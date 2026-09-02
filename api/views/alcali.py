import datetime
import json
from collections import Counter, OrderedDict

from ansi2html import Ansi2HTMLConverter
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.http import (
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
    HttpResponseRedirect,
)
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView
from rest_framework import viewsets
from rest_framework.decorators import (
    action,
    api_view,
    renderer_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from api.backend.salt_api import SaltApiError
from api.backend.netapi import (
    refresh_minion,
    manage_key,
    get_events,
    init_db,
    refresh_schedules,
    run_raw,
    get_keys,
    manage_schedules,
)
from api.management.commands.prune_returns import (
    _delete_by_pk,
    _delete_by_time,
)
from api.models import (
    SaltReturns,
    Keys,
    Minions,
    SaltEvents,
    Jids,
    Schedule,
    Conformity,
    UserSettings,
    MinionsCustomFields,
    Functions,
    JobTemplate,
    AuditLog,
)
from api.audit import AuditedModelViewSet, record
from api.permissions import IsLoggedInUserOrAdmin, IsAdminUser, IsAdminUserOrReadOnly
from api.renderer import StreamingRenderer
from api.serializers import (
    ConformitySerializer,
    UsersSerializer,
    UserSettingsSerializer,
    MinionsCustomFieldsSerializer,
    FunctionsSerializer,
    ScheduleSerializer,
    MyTokenObtainPairSerializer,
    SaltReturnsSerializer,
    JobTemplateSerializer,
    KeysSerializer,
    MinionsSerializer,
    AuditLogSerializer,
)
from api.utils import graph_data, render_conformity, RawCommand
from api.utils.matching import glob_match, list_match, subdict_match
from api.utils.output import highstate_output, nested_output

# Serve Vue Application
index_view = never_cache(TemplateView.as_view(template_name="index.html"))


class KeysViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Keys.objects.all()
    serializer_class = KeysSerializer

    @action(methods=["POST"], detail=False)
    def refresh(self, request):
        ret = get_keys(refresh=True)
        if "error" in ret:
            return Response(ret["error"], status=401)
        return Response(ret)

    @action(detail=False)
    def keys_status(self, request):
        keys_status = list(Keys.objects.values_list("status", flat=True))
        keys_status = dict(Counter(keys_status))
        od = OrderedDict()
        for status in ["accepted", "rejected", "denied", "unaccepted"]:
            if status not in keys_status:
                od[status] = 0
            else:
                od[status] = keys_status[status]
        return Response(od)

    @action(methods=["post"], detail=False)
    def manage_keys(self, request):
        kwargs = {}
        key = request.data.get("target")
        key_action = request.data.get("action")
        if key_action == "accept":
            kwargs = {"include_rejected": True, "include_denied": True}
        elif key_action == "reject":
            kwargs = {"include_accepted": True, "include_denied": True}
        ret = manage_key(key_action, key, kwargs)
        if "error" in ret:
            return Response(ret["error"], status=401)
        record("key.{}".format(key_action), target=key)
        return Response({"result": "{} on {}: done".format(key_action, key)})


class MinionsViewSet(AuditedModelViewSet, viewsets.ModelViewSet):
    queryset = Minions.objects.all()
    serializer_class = MinionsSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_field = "minion_id"
    lookup_value_regex = "[^/]+"

    def get_permissions(self):
        # Refreshing runs test.ping and grains.items through the caller's own
        # Salt credentials, so the master applies their eauth ACL. Deleting a
        # minion only touches Alcali's table, and stays staff only.
        if self.action in (
            "preview_target",
            "refresh_minions",
            "conformity",
            "conformity_detail",
            "silent",
        ):
            # Not `[]`: an empty list means no permission class runs at all,
            # which would open these to anonymous callers.
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=["post"])
    def refresh_minions(self, request):
        if request.data.get("minion_id"):
            minion_id = request.data.get("minion_id")
            ret = refresh_minion(minion_id)
            if "error" in ret:
                return Response(ret["error"], status=401)

            return Response({"result": "refreshed {}".format(minion_id)})

        # Run test.ping to list currently connected minions
        connected = run_raw(
            [
                {
                    "client": "local",
                    "batch": None,
                    "tgt_type": "glob",
                    "tgt": "*",
                    "fun": "test.ping",
                }
            ]
        )
        # run_raw reports a failure by returning {"error": ...}. Without this
        # check a master that cannot be reached produced an empty minion list
        # and a 200, so the UI reported "0 minions refreshed" as a success and
        # the table stayed empty with nothing explaining why.
        if not isinstance(connected, dict):
            return Response(
                {"error": "unexpected response from the Salt API"}, status=502
            )
        if "error" in connected:
            return Response(connected["error"], status=401)

        accepted_minions = [i for i in connected if connected.get(i) is True]
        for minion in accepted_minions:
            ret = refresh_minion(minion)
            if "error" in ret:
                return Response(ret["error"], status=401)
        # A reachable master that answers with nobody is not the same as a
        # successful refresh, and reporting it as one is how an empty Minions
        # page ends up looking like a fleet with no minions. It usually means
        # the master could not read the job back - see the job cache check in
        # `manage.py alcali_check`.
        return Response(
            {
                "refreshed": accepted_minions,
                "responded": len(connected),
                "no_minions_replied": not connected,
            }
        )

    @action(detail=False)
    def preview_target(self, request):
        """Which stored minions a target expression would select.

        Alcali holds every refreshed minion's grains and pillar, so the blast
        radius of a job can be shown before it is published. Only the target
        types that can be evaluated faithfully from that data are answered;
        anything else - compound, pcre, range, nodegroup - reports that it was
        not evaluated rather than guessing, because a wrong blast radius is
        worse than none. The roster is also only as current as the last
        refresh, which the response says.
        """
        expression = request.query_params.get("tgt", "")
        tgt_type = request.query_params.get("tgt_type", "glob")
        supported = {"glob", "list", "grain", "pillar"}
        if tgt_type not in supported:
            return Response(
                {
                    "evaluated": False,
                    "tgt": expression,
                    "tgt_type": tgt_type,
                    "reason": "{} expressions are evaluated by the master, not "
                    "from stored grains".format(tgt_type),
                    "matched": [],
                }
            )

        matched = []
        for minion in Minions.objects.all():
            if tgt_type == "glob":
                hit = glob_match(minion.minion_id, expression or "*")
            elif tgt_type == "list":
                hit = list_match(minion.minion_id, expression)
            else:
                try:
                    data = (
                        minion.loaded_grain()
                        if tgt_type == "grain"
                        else minion.loaded_pillar()
                    )
                except ValueError:
                    continue
                hit = subdict_match(data, expression)
            if hit:
                matched.append(minion.minion_id)
        matched.sort()
        return Response(
            {
                "evaluated": True,
                "tgt": expression,
                "tgt_type": tgt_type,
                "matched": matched,
                "count": len(matched),
                "known_minions": Minions.objects.count(),
            }
        )

    @action(detail=False)
    def silent(self, request):
        """Accepted minions that have not returned anything lately.

        A minion that stops answering leaves no trace in salt_returns - there
        is simply no new row - so nothing in a job or event view shows it. The
        accepted keys are the roster to compare against.
        """
        try:
            days = int(request.query_params.get("days", 1))
        except (TypeError, ValueError):
            days = 1
        days = max(1, min(days, 365))
        cutoff = timezone.now() - datetime.timedelta(days=days)

        accepted = list(
            Keys.objects.filter(status="accepted").values_list("minion_id", flat=True)
        )
        # One grouped query for the whole roster rather than one per minion.
        last_seen = dict(
            SaltReturns.objects.filter(id__in=accepted)
            .values_list("id")
            .annotate(last=Max("alter_time"))
            .values_list("id", "last")
        )
        inventoried = set(
            Minions.objects.filter(minion_id__in=accepted).values_list(
                "minion_id", flat=True
            )
        )

        silent = []
        for minion_id in accepted:
            last = last_seen.get(minion_id)
            if last is not None and last >= cutoff:
                continue
            silent.append(
                {
                    "minion_id": minion_id,
                    "last_job": last,
                    "days": (timezone.now() - last).days if last else None,
                    "reason": "never returned" if last is None else "stale",
                    "inventoried": minion_id in inventoried,
                }
            )
        silent.sort(key=lambda row: (row["last_job"] is not None, row["last_job"]))
        return Response(
            {
                "threshold_days": days,
                "accepted": len(accepted),
                "silent": silent,
            }
        )

    @action(detail=False)
    def conformity(self, request):
        highstate_conformity = {"conform": 0, "conflict": 0, "unknown": 0}
        for minion in Minions.objects.all():
            conformity = minion.conformity()
            if conformity is True:
                highstate_conformity["conform"] += 1
            elif conformity is False:
                highstate_conformity["conflict"] += 1
            else:
                highstate_conformity["unknown"] += 1

        conformity_name, conformity_data, _ = render_conformity()
        conformity_name.insert(0, "HIGHSTATE")
        conformity_data.insert(0, highstate_conformity)
        return Response({"name": conformity_name, "data": conformity_data})

    @action(detail=True)
    def conformity_detail(self, request, minion_id):
        minion = self.get_object()

        # Get conformity data.
        _, _, custom_conformity = render_conformity(minion.minion_id)
        custom_conformity = (
            custom_conformity[minion.minion_id] if custom_conformity else None
        )
        minion_conformity = minion.conformity()

        # Convert states to html.
        conv = Ansi2HTMLConverter(inline=True, scheme="xterm")
        last_highstate = minion.last_highstate()
        succeeded, unchanged, failed = {}, {}, {}

        if last_highstate:
            last_highstate = last_highstate.loaded_ret()["return"]
            # Sls error
            if isinstance(last_highstate, list):
                failed = {"error": last_highstate[0]}
            else:
                for state in last_highstate:
                    state_name = state.split("_|-")[1]
                    formatted = highstate_output.output(
                        {minion.minion_id: {state: last_highstate[state]}},
                        summary=False,
                    )
                    if last_highstate[state]["result"] is True:
                        succeeded[state_name] = conv.convert(
                            formatted, ensure_trailing_newline=True
                        )
                    elif last_highstate[state]["result"] is None:
                        unchanged[state_name] = conv.convert(
                            formatted, ensure_trailing_newline=True
                        )
                    else:
                        failed[state_name] = conv.convert(
                            formatted, ensure_trailing_newline=True
                        )
        return Response(
            {
                "custom_conformity": custom_conformity,
                "conformity": minion_conformity,
                "succeeded": succeeded,
                "unchanged": unchanged,
                "failed": failed,
            }
        )


class MinionsCustomFieldsViewSet(AuditedModelViewSet, viewsets.ModelViewSet):
    queryset = MinionsCustomFields.objects.all()
    serializer_class = MinionsCustomFieldsSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def perform_create(self, serializer):
        for minion in Minions.objects.all():
            serializer.save(minion=minion)

    @action(methods=["post"], detail=False)
    def delete_field(self, request):
        field = request.data.get("name")
        MinionsCustomFields.objects.filter(name=field).delete()
        record("minionscustomfields.delete", target=field)
        return Response({"result": "{} field deleted".format(field)})


class ConformityViewSet(AuditedModelViewSet, viewsets.ModelViewSet):
    queryset = Conformity.objects.all()
    serializer_class = ConformitySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    lookup_value_regex = "[0-9a-zA-Z.]+"

    @action(detail=False)
    def render(self, request):
        conformity_name = [i.name for i in Conformity.objects.all()]
        default_columns = [
            {"text": "Minion id", "value": "minion_id"},
            {"text": "Last Highstate", "value": "last_highstate"},
            {"text": "Highstate Conformity", "value": "conformity"},
            {"text": "Succeeded", "value": "succeeded"},
            {"text": "Unchanged", "value": "unchanged"},
            {"text": "Failed", "value": "failed"},
        ]
        for conformity in conformity_name:
            default_columns.append({"text": conformity, "value": conformity})

        # Get conformity data.
        _, _, rendered_conformity = render_conformity()
        # Compute number of succeeded, unchanged and failed states.
        conformity_data = []
        minions = Minions.objects.all()
        for minion in minions:
            succeeded, unchanged, failed = 0, 0, 0
            last_highstate = minion.last_highstate()
            if last_highstate:
                last_highstate_date = last_highstate.alter_time
                last_highstate = last_highstate.loaded_ret()["return"]
                # Sls error
                if isinstance(last_highstate, list):
                    succeeded, unchanged, failed = None, None, 1
                else:
                    for state in last_highstate:
                        if last_highstate[state]["result"] is True:
                            succeeded += 1
                        elif last_highstate[state]["result"] is None:
                            unchanged += 1
                        else:
                            failed += 1
            else:
                last_highstate_date, succeeded, unchanged, failed = (
                    None,
                    None,
                    None,
                    None,
                )

            default_conformity = {
                "minion_id": minion.minion_id,
                "last_highstate": last_highstate_date,
                "conformity": "Unknown"
                if minion.conformity() is None
                else str(minion.conformity()),
                "succeeded": succeeded,
                "unchanged": unchanged,
                "failed": failed,
            }
            # Add custom conformity values to datatable data.
            if rendered_conformity:
                for conformity in rendered_conformity[minion.minion_id]:
                    default_conformity.update(conformity)
            conformity_data.append(default_conformity)
        return Response({"name": default_columns, "data": conformity_data})


class FunctionsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Functions.objects.all()
    serializer_class = FunctionsSerializer


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer

    def list(self, request, *args, **kwargs):
        # Datatable.
        ret = []
        for schedule in Schedule.objects.values():
            for k, v in json.loads(schedule["job"]).items():
                schedule[k] = v
            del schedule["job"]
            ret.append(schedule)
        return Response(ret)

    @action(methods=["POST"], detail=False)
    def refresh(self, request):
        ret = refresh_schedules()
        if "error" in ret:
            return Response(ret["error"], status=401)
        return Response({"result": "refreshed"})

    @action(methods=["POST"], detail=False)
    def manage(self, request):
        action = request.data.get("action")
        minion = request.data.get("minion")
        name = request.data.get("name")
        ret = manage_schedules(action, name, minion)
        if not ret:
            return Response({"result": "not good"})
        if "error" in ret:
            return Response(ret["error"], status=401)
        record("schedule.{}".format(action), target="{}:{}".format(minion, name))
        return Response(
            {"result": "schedule " + name + " on " + minion + " " + action + "d"}
        )


class UsersViewSet(AuditedModelViewSet, viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UsersSerializer

    def get_queryset(self):
        if not self.request.user.is_staff:
            return User.objects.filter(id=self.request.user.id)
        else:
            return User.objects.all()

    def get_permissions(self):
        permission_classes = []
        # Only Staff users are allowed to create users.
        if self.action == "create":
            permission_classes = [IsAdminUser]
        elif self.action in ["retrieve", "update", "partial_update", "list"]:
            permission_classes = [IsLoggedInUserOrAdmin]
        elif self.action == "destroy":
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    @action(methods=["POST"], detail=True)
    def manage_token(self, request, pk):
        user = self.get_object()
        action = request.data.get("action")
        if action == "renew":
            user.user_settings.generate_token()
        elif action == "revoke":
            user.user_settings.token = "REVOKED"
            user.user_settings.save()
        record("token.{}".format(action), target=user.username)
        return Response({"result": "{} successful".format(action)})


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Who changed what in Alcali itself.

    Jobs are traceable through Salt's own jids table; these are the changes
    that never reach the master.
    """

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("user")
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)
        try:
            limit = int(self.request.query_params.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        return queryset[: max(1, min(limit, 2000))]


class UserSettingsViewSet(viewsets.ModelViewSet):
    queryset = UserSettings.objects.all()
    serializer_class = UserSettingsSerializer

    def get_queryset(self):
        # These rows hold each user's Salt token, which is the credential they
        # authenticate to the master with. Without this filter any logged in
        # user could read - and overwrite - everyone else's.
        if self.request.user.is_staff:
            return UserSettings.objects.all()
        return UserSettings.objects.filter(user=self.request.user)


class JobTemplateViewSet(AuditedModelViewSet, viewsets.ModelViewSet):
    queryset = JobTemplate.objects.all()
    serializer_class = JobTemplateSerializer
    permission_classes = [IsAdminUserOrReadOnly]


@api_view(["GET"])
def jobs_graph(request):
    id = request.query_params.get("id", None)
    params = {
        "period": int(request.query_params.get("period", 7)),
        "fun": request.query_params.get("fun", "all"),
    }
    if id:
        params.update(id=id)
    days, count, error_count = graph_data(**params)
    return Response({"labels": days, "series": [count, error_count]})


@api_view(["POST"])
def parse_modules(request):
    if request.data.get("target"):
        ret = init_db(request.data.get("target"))
        if "error" in ret:
            return Response(ret["error"], status=401)
        return Response(ret)


@api_view(["GET"])
def search(request):
    if request.query_params.get("q", None):
        query = request.query_params.get("q")
        # First try to match minions.
        minion_results = []
        return_results = []
        # Grains and pillar are stored as JSON text, so a substring match over
        # them finds a minion by anything Salt knows about it - an address, a
        # MAC, a kernel version - not just by name.
        minion_query = Minions.objects.filter(
            Q(minion_id__icontains=query)
            | Q(grain__icontains=query)
            | Q(pillar__icontains=query)
        )
        return_query = SaltReturns.objects.filter(
            Q(jid__icontains=query) | Q(fun__icontains=query)
        )[:200]
        if minion_query:
            for res in minion_query:
                minion = MinionsSerializer(res)
                minion_results.append(minion.data)
        if return_query:
            for res in return_query:
                job = SaltReturnsSerializer(res)
                return_results.append(job.data)
        return Response(
            {"minions": minion_results, "jobs": return_results, "query": query}
        )

        # Return to referer
    return HttpResponseRedirect(request.META.get("HTTP_REFERER"))


@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def prune(request):
    """Report or apply the returner retention window.

    Salt's mysql returner never deletes anything - keep_jobs_seconds governs
    the master's own job cache, not this database - so these tables grow for
    the life of the installation. GET reports what a window would remove;
    POST removes it. Staff only, since it destroys history.
    """
    try:
        days = int(request.query_params.get("days") or request.data.get("days") or 30)
    except (TypeError, ValueError):
        return Response({"error": "days must be a whole number"}, status=400)
    try:
        events_days = int(
            request.query_params.get("events_days")
            or request.data.get("events_days")
            or days
        )
    except (TypeError, ValueError):
        return Response({"error": "events_days must be a whole number"}, status=400)
    if days < 1 or events_days < 1:
        return Response({"error": "a window of less than a day is not allowed"}, status=400)

    now = timezone.now()
    returns_before = now - datetime.timedelta(days=days)
    events_before = now - datetime.timedelta(days=events_days)
    returns = SaltReturns.objects.filter(alter_time__lt=returns_before)
    events = SaltEvents.objects.filter(alter_time__lt=events_before)
    stale_jids = Jids.objects.exclude(
        jid__in=SaltReturns.objects.exclude(alter_time__lt=returns_before).values("jid")
    )
    counts = {
        "salt_returns": returns.count(),
        "salt_events": events.count(),
        "jids": stale_jids.count(),
    }
    body = {
        "days": days,
        "events_days": events_days,
        "matched": counts,
        "totals": {
            "salt_returns": SaltReturns.objects.count(),
            "salt_events": SaltEvents.objects.count(),
            "jids": Jids.objects.count(),
        },
    }
    if request.method == "GET":
        body["applied"] = False
        return Response(body)

    deleted = {
        # salt_returns has no unique key, so this must delete on the time
        # predicate and never by pk - see prune_returns.
        "salt_returns": _delete_by_time(SaltReturns, returns_before),
        "salt_events": _delete_by_pk(SaltEvents, events),
        "jids": _delete_by_pk(Jids, stale_jids),
    }
    record("returner.prune", target="{} day(s)".format(days), detail=deleted)
    body["applied"] = True
    body["deleted"] = deleted
    return Response(body)


@api_view(["GET"])
def stats(request):
    # Status widget.
    jobs_nb = SaltReturns.objects.count()
    events_nb = SaltEvents.objects.count()
    schedules_nb = Schedule.objects.count()
    return Response({"jobs": jobs_nb, "events": events_nb, "schedules": schedules_nb})


@api_view(["GET"])
def version(request):
    return Response({"version": settings.VERSION})


@api_view(["GET"])
@renderer_classes([StreamingRenderer, JSONRenderer])
def event_stream(request):
    try:
        stream = get_events()
    except SaltApiError as exc:
        # A real status, so the client can tell a live stream from a master it
        # cannot reach, instead of both looking like a 200.
        return Response({"error": str(exc)}, status=503)
    response = StreamingHttpResponse(
        stream, status=200, content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    return response


@api_view(["POST"])
def run(request):
    if not request.data.get("raw"):
        return Response({"error": "no command submitted"}, status=400)
    command = RawCommand(request.data.get("command"))
    parsed_command = command.parse()
    # Schedules.
    if request.data.get("schedule_type"):
        schedule_type = request.data.get("schedule_type")
        schedule_name = request.data.get(
            "schedule_name", datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        )
        schedule_parsed = [
            {
                "client": "local",
                "batch": None,
                "tgt_type": parsed_command[0]["tgt_type"],
                "tgt": parsed_command[0]["tgt"],
                "fun": "schedule.add",
                "arg": [
                    schedule_name,
                    "function={}".format(parsed_command[0]["fun"]),
                    "job_args={}".format(parsed_command[0]["arg"]),
                ],
            }
        ]
        if schedule_type == "once":
            schedule_date = request.data.get("schedule")
            schedule_parsed[0]["arg"].append("once={}".format(schedule_date))
            schedule_parsed[0]["arg"].append("once_fmt=%Y-%m-%d %H:%M:%S")
        else:
            cron = request.data.get("cron")
            schedule_parsed[0]["arg"].append("cron={}".format(cron))
        ret = run_raw(schedule_parsed)
        if "error" in ret:
            return Response(ret["error"], status=401)
        formatted = nested_output.output(ret)
        conv = Ansi2HTMLConverter(inline=True, scheme="xterm")
        html = conv.convert(formatted, ensure_trailing_newline=True)
        return HttpResponse(html)

    cli_ret = request.data.get("cli")
    conv = Ansi2HTMLConverter(inline=True, scheme="xterm")
    ret = run_raw(parsed_command)
    if "error" in ret:
        return Response(ret["error"], status=401)
    formatted = "\n"

    # Error.
    if isinstance(ret, str):
        item_ret = nested_output.output(ret)
        formatted += item_ret + "\n\n"
    # runner or wheel client.
    elif isinstance(ret, list):
        for item in ret:
            item_ret = nested_output.output(item)
            formatted += item_ret + "\n\n"
    # Highstate.
    elif (
        parsed_command[0]["fun"] in ["state.apply", "state.highstate"]
        and parsed_command[0]["client"] != "local_async"
    ):
        for state, out in ret.items():
            minion_ret = highstate_output.output({state: out})
            formatted += minion_ret + "\n\n"
    # Everything else.
    else:
        for state, out in ret.items():
            minion_ret = nested_output.output({state: out})
            formatted += minion_ret + "\n\n"

    if cli_ret:
        return JsonResponse({"results": formatted})
    html = conv.convert(formatted, ensure_trailing_newline=True)
    return HttpResponse(html)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(["POST"])
@permission_classes([AllowAny])
def verify(request):
    username = request.data.get("username")
    password = request.data.get("password")
    if not username or not password:
        return HttpResponse("Unauthorized", status=401)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return HttpResponse("Unauthorized", status=401)
    # Compared in constant time: this is the Salt token, and a plain ==
    # leaks its length and prefix through the response timing.
    if constant_time_compare(password, user.user_settings.token):
        return Response([])
    return HttpResponse("Unauthorized", status=401)


@api_view(["GET"])
@permission_classes([AllowAny])
def social(request):
    return Response(
        {
            "client_id": settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
            "provider": "google-oauth2",
            "redirect_uri": settings.SOCIAL_AUTH_REDIRECT_URI,
        }
    )
