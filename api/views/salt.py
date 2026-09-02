import datetime
import json

from ansi2html import Ansi2HTMLConverter
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.models import SaltReturns, SaltEvents, Jids
from api.serializers import SaltReturnsSerializer, EventsSerializer
from api.utils.output import highstate_output, nested_output


# salt_returns.success is a varchar the returner fills in; different Salt
# versions have written "1"/"0" and "True"/"False" into it.
TRUE_VALUES = ["1", "True", "true", "yes"]
FALSE_VALUES = ["0", "False", "false", "no", ""]


# jids.load also carries the master's publish key and, on some versions, an
# eauth token in kwargs. Nothing outside this allowlist is exposed.
PUBLISHED_LOAD_FIELDS = ("user", "tgt", "tgt_type", "fun", "arg", "metadata")


def jid_loads(jids):
    """Map jid -> the publish payload, filtered to what is safe to show."""
    loads = {}
    for jid, raw in Jids.objects.filter(jid__in=list(jids)).values_list(
        "jid", "load"
    ):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        loads[jid] = {k: payload.get(k) for k in PUBLISHED_LOAD_FIELDS}
    return loads


def jid_users(jids):
    """Map jid -> submitting user in one query.

    `SaltReturns.user()` otherwise fetches the jids row per result, which turns
    a page of jobs into one query per row against the returner database.
    """
    return {jid: load.get("user") or "" for jid, load in jid_loads(jids).items()}


class MultipleFieldLookupMixin(object):
    """
    Apply this mixin to any view or viewset to get multiple field filtering
    based on a `lookup_fields` attribute, instead of the default single field filtering.
    """

    def get_object(self):
        queryset = self.get_queryset()  # Get the base queryset
        queryset = self.filter_queryset(queryset)  # Apply any filter backends
        filter = {}
        for field in self.lookup_fields:
            if self.kwargs[field]:  # Ignore empty fields.
                filter[field] = self.kwargs[field]
        obj = get_object_or_404(queryset, **filter)  # Lookup the object
        self.check_object_permissions(self.request, obj)
        return obj


class SaltReturnsList(generics.ListAPIView):
    serializer_class = SaltReturnsSerializer

    def get_queryset(self):
        queryset = SaltReturns.objects.all().defer("return_field")
        qry = {}
        start = self.request.query_params.get("start", None)
        end = self.request.query_params.get("end", None)
        try:
            limit = int(self.request.query_params.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 5000))
        target = self.request.query_params.getlist("target[]")
        users = self.request.query_params.getlist("users[]", None)
        functions = self.request.query_params.getlist("functions[]")
        success = self.request.query_params.get("success")
        if target:
            if len(target) > 1:
                qry["id__in"] = target
            else:
                qry["id"] = target[0]
        if functions:
            qry["fun__in"] = functions
        if start and end:
            qry["alter_time__date__range"] = [start, end]

        queryset = queryset.filter(**qry)

        # The returner writes its own verdict to salt_returns.success, so a
        # "show me what failed" query can be answered in SQL instead of pulling
        # every row into Python to re-derive it from full_ret.
        if success in ("true", "false"):
            wanted = success == "true"
            queryset = queryset.filter(
                success__in=TRUE_VALUES if wanted else FALSE_VALUES
            )

        queryset = list(queryset.order_by("-alter_time")[:limit])
        self._jid_users = jid_users({i.jid for i in queryset})
        if users:
            queryset = [i for i in queryset if self._jid_users.get(i.jid, "") in users]
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["jid_users"] = getattr(self, "_jid_users", None)
        return context


class SaltReturnsListJid(generics.ListAPIView):
    serializer_class = SaltReturnsSerializer

    def get_queryset(self):
        jid = self.kwargs["jid"]
        return SaltReturns.objects.filter(jid=jid).defer("return_field").order_by(
            "-alter_time"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["jid_users"] = jid_users([self.kwargs["jid"]])
        return context


@api_view(["GET"])
def job_summary(request, jid):
    """Reconcile what a job was published to against what came back.

    salt_returns only ever gets a row from a minion that answered, so a job
    that timed out on some of its targets looks complete in the jobs table.
    The salt/job/<jid>/new event carries the list the master expected, which is
    the only record of the minions that never replied.
    """
    published = []
    for data in SaltEvents.objects.filter(
        tag="salt/job/{}/new".format(jid)
    ).values_list("data", flat=True):
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            continue
        for minion in payload.get("minions") or []:
            if minion not in published:
                published.append(minion)

    returned, succeeded, failed = [], [], []
    for row in SaltReturns.objects.filter(jid=jid).defer("return_field"):
        returned.append(row.id)
        (succeeded if row.success_bool() is True else failed).append(row.id)

    # No `new` event (pruned, or the master never wrote one) means the expected
    # roster is unknown - which is not the same as "nothing is missing".
    missing = [m for m in published if m not in returned] if published else []
    load = jid_loads([jid]).get(jid) or {}
    return Response(
        {
            "jid": jid,
            "published_to": published,
            "expected_known": bool(published),
            "returned": returned,
            "succeeded": succeeded,
            "failed": failed,
            "missing": missing,
            # What was actually asked for, as opposed to who happened to answer.
            "target": load.get("tgt"),
            "target_type": load.get("tgt_type"),
            "function": load.get("fun"),
            "arguments": load.get("arg"),
            "user": load.get("user"),
            "metadata": load.get("metadata"),
        }
    )


@api_view(["GET"])
def state_durations(request):
    """Where highstate time actually goes, across the fleet.

    Every state in a highstate return carries `duration` (milliseconds),
    `start_time` and `__sls__` alongside its result. Alcali renders the newest
    run as coloured HTML and drops the rest, so nothing answers "which state is
    costing us a minute on every run".
    """
    try:
        days = int(request.query_params.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, 365))
    minion = request.query_params.get("id")

    since = timezone.now() - datetime.timedelta(days=days)
    rows = SaltReturns.objects.filter(
        Q(fun="state.apply") | Q(fun="state.highstate"), alter_time__gte=since
    ).defer("return_field")
    if minion:
        rows = rows.filter(id=minion)

    # A single state's per-minion detail rather than the fleet aggregate:
    # which minions run it, what it costs each of them, and where it last
    # failed or last made changes.
    wanted = request.query_params.get("state")
    if wanted:
        detail = []
        for row in rows.order_by("-alter_time").iterator():
            payload = row.loaded_ret().get("return")
            if not isinstance(payload, dict):
                continue
            for key, result in payload.items():
                if not isinstance(result, dict):
                    continue
                if (result.get("__id__") or _state_name(key)) != wanted:
                    continue
                if any(seen["minion"] == row.id for seen in detail):
                    continue  # newest run per minion
                detail.append(
                    {
                        "minion": row.id,
                        "jid": row.jid,
                        "when": row.alter_time,
                        "sls": result.get("__sls__") or "",
                        "duration_ms": round(result.get("duration") or 0, 1),
                        "result": result.get("result"),
                        "changed": bool(result.get("changes")),
                        "comment": (result.get("comment") or "")[:400],
                    }
                )
        detail.sort(key=lambda row: row["duration_ms"], reverse=True)
        return Response({"state": wanted, "days": days, "minions": detail})

    states = {}
    runs = 0
    for row in rows.iterator():
        payload = row.loaded_ret().get("return")
        # A failed render returns a list of error strings, not a state map.
        if not isinstance(payload, dict):
            continue
        runs += 1
        for key, result in payload.items():
            if not isinstance(result, dict):
                continue
            duration = result.get("duration")
            if not isinstance(duration, (int, float)):
                continue
            name = result.get("__id__") or _state_name(key)
            bucket = states.setdefault(
                name,
                {
                    "state": name,
                    "sls": result.get("__sls__") or "",
                    "runs": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                    "changed": 0,
                    "failed": 0,
                    "minions": set(),
                },
            )
            bucket["runs"] += 1
            bucket["total_ms"] += duration
            bucket["max_ms"] = max(bucket["max_ms"], duration)
            bucket["minions"].add(row.id)
            if result.get("changes"):
                bucket["changed"] += 1
            if result.get("result") is False:
                bucket["failed"] += 1

    summary = []
    for bucket in states.values():
        bucket["minions"] = len(bucket["minions"])
        bucket["mean_ms"] = round(bucket["total_ms"] / bucket["runs"], 1)
        bucket["total_ms"] = round(bucket["total_ms"], 1)
        bucket["max_ms"] = round(bucket["max_ms"], 1)
        # A state reporting changes on nearly every run is not converged; it is
        # being re-applied each time.
        bucket["change_rate"] = round(bucket["changed"] / bucket["runs"], 3)
        summary.append(bucket)
    summary.sort(key=lambda b: b["total_ms"], reverse=True)
    return Response({"days": days, "highstates": runs, "states": summary})


def _state_name(key):
    """`pkg_|-nginx_|-nginx_|-installed` -> `nginx`, falling back to the key."""
    parts = key.split("_|-")
    return parts[1] if len(parts) > 2 else key


@api_view(["GET"])
def jobs_filters(request):
    # Filter options.
    user_list = list(set(jid_users(Jids.objects.values_list("jid", flat=True)).values()))
    minion_list = SaltReturns.objects.values_list("id", flat=True).distinct()
    function_list = (
        SaltReturns.objects.values_list("fun", flat=True).distinct().order_by("fun")
    )
    return Response(
        {
            "users": user_list,
            "minions": minion_list,
            "functions": list(function_list),
        }
    )


class SaltReturnsRetrieve(MultipleFieldLookupMixin, generics.RetrieveAPIView):
    queryset = SaltReturns.objects.all().defer("return_field").order_by("-alter_time")
    serializer_class = SaltReturnsSerializer
    lookup_fields = ["jid", "id"]


@api_view(["GET"])
def job_rendered(request, jid, minion_id):
    # Retrieve job from database.
    job = SaltReturns.objects.get(jid=jid, id=minion_id)

    # Use different output.
    if job.fun in ["state.apply", "state.highstate"]:
        formatted = highstate_output.output({minion_id: job.loaded_ret()["return"]})
    else:
        formatted = nested_output.output({minion_id: job.loaded_ret()["return"]})

    # Convert it to html.
    conv = Ansi2HTMLConverter(inline=True, scheme="xterm")
    html_detail = conv.convert(formatted, ensure_trailing_newline=True)
    return Response(html_detail)


class EventsViewSet(viewsets.ReadOnlyModelViewSet):
    """The most recent Salt events.

    The returner table grows without bound, so this is always a window on the
    newest rows. `limit` moves the window; the total is reported in the
    X-Total-Count header so a caller can tell it is seeing a truncated view.
    """

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 1000

    queryset = SaltEvents.objects.all().order_by("-alter_time")
    serializer_class = EventsSerializer

    def get_limit(self):
        try:
            limit = int(self.request.query_params.get("limit", self.DEFAULT_LIMIT))
        except (TypeError, ValueError):
            return self.DEFAULT_LIMIT
        return max(1, min(limit, self.MAX_LIMIT))

    def get_queryset(self):
        return SaltEvents.objects.all().order_by("-alter_time")[: self.get_limit()]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response["X-Total-Count"] = str(SaltEvents.objects.count())
        return response
