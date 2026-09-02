import json

from ansi2html import Ansi2HTMLConverter
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.models import SaltReturns, SaltEvents, Jids
from api.serializers import SaltReturnsSerializer, EventsSerializer
from api.utils.output import highstate_output, nested_output


def jid_users(jids):
    """Map jid -> submitting user in one query.

    `SaltReturns.user()` otherwise fetches the jids row per result, which turns
    a page of jobs into one query per row against the returner database.
    """
    users = {}
    for jid, load in Jids.objects.filter(jid__in=list(jids)).values_list(
        "jid", "load"
    ):
        try:
            users[jid] = json.loads(load).get("user", "")
        except (TypeError, ValueError):
            users[jid] = ""
    return users


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
        queryset = SaltReturns.objects.all()
        qry = {}
        start = self.request.query_params.get("start", None)
        end = self.request.query_params.get("end", None)
        limit = int(self.request.query_params.get("limit", 50))
        target = self.request.query_params.getlist("target[]")
        users = self.request.query_params.getlist("users[]", None)
        if target:
            if len(target) > 1:
                qry["id__in"] = target
            else:
                qry["id"] = target[0]
        if start and end:
            qry["alter_time__date__range"] = [start, end]

        queryset = list(queryset.filter(**qry).order_by("-alter_time")[:limit])
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
        return SaltReturns.objects.filter(jid=jid).order_by("-alter_time")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["jid_users"] = jid_users([self.kwargs["jid"]])
        return context


@api_view(["GET"])
def jobs_filters(request):
    # Filter options.
    user_list = list(set(jid_users(Jids.objects.values_list("jid", flat=True)).values()))
    minion_list = SaltReturns.objects.values_list("id", flat=True).distinct()
    return Response({"users": user_list, "minions": minion_list})


class SaltReturnsRetrieve(MultipleFieldLookupMixin, generics.RetrieveAPIView):
    queryset = SaltReturns.objects.all().order_by("-alter_time")
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
    conv = Ansi2HTMLConverter(inline=False, scheme="xterm")
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
