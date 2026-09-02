import os

from django.urls import path, include, re_path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views.salt import (
    SaltReturnsList,
    SaltReturnsRetrieve,
    EventsViewSet,
    jobs_filters,
    active_jobs,
    kill_job,
    job_rendered,
    job_summary,
    state_durations,
    SaltReturnsListJid,
)

from api.views.alcali import (
    index_view,
    KeysViewSet,
    MinionsViewSet,
    jobs_graph,
    stats,
    prune,
    event_stream,
    parse_modules,
    ConformityViewSet,
    UsersViewSet,
    MinionsCustomFieldsViewSet,
    FunctionsViewSet,
    run,
    UserSettingsViewSet,
    ScheduleViewSet,
    BeaconViewSet,
    NotificationRuleViewSet,
    MyTokenObtainPairView,
    search,
    verify,
    version,
    diagnostics,
    available_states,
    JobTemplateViewSet,
    AuditLogViewSet,
    social,
)
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r"keys", KeysViewSet)
router.register(r"minions", MinionsViewSet)
router.register(r"events", EventsViewSet)
router.register(r"conformity", ConformityViewSet)
router.register(r"users", UsersViewSet)
router.register(r"userssettings", UserSettingsViewSet)
router.register(r"minionsfields", MinionsCustomFieldsViewSet)
router.register(r"functions", FunctionsViewSet)
router.register(r"schedules", ScheduleViewSet)
router.register(r"beacons", BeaconViewSet)
router.register(r"notifications", NotificationRuleViewSet)
router.register(r"job_templates", JobTemplateViewSet)
router.register(r"audit", AuditLogViewSet)

urlpatterns = [
    path("", index_view, name="index"),
    path("api/token/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),
    path("api/search/", search, name="search"),
    path("api/stats/", stats, name="stats"),
    path("api/prune/", prune, name="prune"),
    path("api/version/", version, name="version"),
    path("api/diagnostics/", diagnostics, name="diagnostics"),
    path("api/states/available/", available_states, name="states-available"),
    path("api/settings/initdb", parse_modules, name="parse_modules"),
    path("api/event_stream/", event_stream, name="event_stream"),
    path("api/jobs/", SaltReturnsList.as_view(), name="jobs-list"),
    path("api/jobs/filters/", jobs_filters, name="jobs-filters"),
    # Before the <str:jid> routes below, which would otherwise swallow it.
    path("api/jobs/active/", active_jobs, name="jobs-active"),
    path("api/jobs/<str:jid>/kill/", kill_job, name="jobs-kill"),
    path("api/run/", run, name="run"),
    # Ahead of the <jid>/<id> detail route, which would otherwise match this
    # with id="summary".
    path("api/jobs/<str:jid>/summary/", job_summary, name="jobs-summary"),
    path(
        "api/jobs/<str:jid>/<str:id>/",
        SaltReturnsRetrieve.as_view(),
        name="jobs-detail",
    ),
    path("api/jobs/<str:jid>/", SaltReturnsListJid.as_view(), name="jobs-list-jid"),
    path(
        "api/jobs/<str:jid>/<str:minion_id>/rendered_state/",
        job_rendered,
        name="jobs-detail-rendered",
    ),
    path("api/jobs/graph", jobs_graph, name="jobs_graph"),
    path("api/states/durations/", state_durations, name="state-durations"),
]

# The frontend routes on the History API, so a direct hit or a refresh on
# /minions, /jobs/<jid>/<id>, /login ... arrives here and must be answered with
# the SPA shell. Kept last, and never shadowing the API or the static files.
spa_fallback = re_path(r"^(?!api/|static/).*$", index_view, name="spa")

if os.environ.get("SALT_AUTH", "rest") == "rest":
    urlpatterns += [path("api/token/verify/", verify, name="token_verify")]

if os.environ.get("AUTH_BACKEND") and os.environ["AUTH_BACKEND"].lower() == "social":
    from rest_social_auth.views import SocialJWTPairUserAuthView

    urlpatterns += [
        path("api/social/", social, name="social"),
        path(
            "api/social/login/",
            SocialJWTPairUserAuthView.as_view(),
            name="social_login",
        ),
    ]

urlpatterns += [spa_fallback]
