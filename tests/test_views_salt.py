import json
import pytest
from api.models import SaltReturns, SaltEvents, Jids


@pytest.mark.django_db()
def test_salt_returns_list(admin_client, jwt):
    response = admin_client.get("/api/jobs/", **jwt)
    assert len(response.json()) == SaltReturns.objects.count()
    assert response.status_code == 200


@pytest.mark.django_db()
def test_salt_returns_filters(jid, highstate, admin_client, jwt):
    highstate()
    response = admin_client.get("/api/jobs/filters/", **jwt)
    assert "2e220fd40bc5" in response.json()["minions"]
    assert response.status_code == 200


@pytest.mark.django_db()
def test_salt_returns_list_filtered(jid, highstate, admin_client, jwt):
    highstate()
    response = admin_client.get("/api/jobs/?limit=1&target[]=2e220fd40bc5", **jwt)
    assert len(response.json()) <= 1
    assert response.status_code == 200


@pytest.mark.django_db()
def test_salt_returns_job(jid, highstate, admin_client, jwt):
    highstate()
    assert SaltReturns.objects.get(jid="20190429180928455927", id="2e220fd40bc5")
    response = admin_client.get("/api/jobs/20190429180928455927/2e220fd40bc5/", **jwt)
    assert response.json()["jid"] == "20190429180928455927"
    assert response.status_code == 200


@pytest.mark.django_db()
def test_salt_returns_list(admin_client, jwt):
    response = admin_client.get("/api/events/", **jwt)
    assert len(response.json()) <= 200
    assert response.status_code == 200


@pytest.mark.django_db()
def test_salt_returns_job_rendered(jid, highstate, admin_client, jwt):
    highstate()
    assert SaltReturns.objects.get(jid="20190429180928455927", id="2e220fd40bc5")
    response = admin_client.get(
        "/api/jobs/20190429180928455927/2e220fd40bc5/rendered_state/", **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_jobs_filter_by_function(admin_client, jwt, highstate, jid):
    highstate()
    response = admin_client.get("/api/jobs/?functions[]=state.apply", **jwt)
    assert response.status_code == 200
    assert {row["fun"] for row in response.json()} == {"state.apply"}

    response = admin_client.get("/api/jobs/?functions[]=test.ping", **jwt)
    assert response.json() == []


@pytest.mark.django_db()
def test_jobs_filter_by_success(admin_client, jwt, highstate, jid):
    highstate()
    SaltReturns.objects.filter(fun="state.apply").update(success="0")
    assert admin_client.get("/api/jobs/?success=true", **jwt).json() == []
    failed = admin_client.get("/api/jobs/?success=false", **jwt).json()
    assert len(failed) == 1


@pytest.mark.django_db()
def test_jobs_list_omits_the_payload_columns(admin_client, jwt, highstate, jid):
    highstate()
    row = admin_client.get("/api/jobs/", **jwt).json()[0]
    # A highstate payload is large and nothing renders it; the detail view
    # fetches formatted output from /rendered_state/ instead.
    assert "full_ret" not in row and "return_field" not in row
    # The fields derived from full_ret still resolve.
    assert set(row) >= {"jid", "id", "fun", "arguments", "success", "user"}


@pytest.mark.django_db()
def test_jobs_filters_lists_functions(admin_client, jwt, highstate, jid):
    highstate()
    body = admin_client.get("/api/jobs/filters/", **jwt).json()
    assert "state.apply" in body["functions"]


@pytest.mark.django_db()
def test_job_summary_reports_minions_that_never_returned(admin_client, jwt):
    jid = "20200101000000000009"
    SaltEvents.objects.create(
        tag="salt/job/{}/new".format(jid),
        data='{"jid": "%s", "fun": "test.ping", "minions": '
             '["minion1", "minion2", "minion3"]}' % jid,
        alter_time="2020-01-01 00:00:00", master_id="master",
    )
    for minion, ok in (("minion1", "true"), ("minion2", "false")):
        SaltReturns.objects.create(
            fun="test.ping", jid=jid, return_field="{}", id=minion,
            success="1", alter_time="2020-01-01 00:00:01",
            full_ret='{"success": %s, "fun_args": []}' % ok,
        )
    body = admin_client.get("/api/jobs/{}/summary/".format(jid), **jwt).json()
    assert body["expected_known"] is True
    assert sorted(body["published_to"]) == ["minion1", "minion2", "minion3"]
    assert sorted(body["returned"]) == ["minion1", "minion2"]
    assert body["succeeded"] == ["minion1"]
    assert body["failed"] == ["minion2"]
    # The whole point: minion3 answered nothing and appears nowhere else.
    assert body["missing"] == ["minion3"]


@pytest.mark.django_db()
def test_job_summary_without_a_new_event_does_not_invent_a_roster(admin_client, jwt):
    jid = "20200101000000000010"
    SaltReturns.objects.create(
        fun="test.ping", jid=jid, return_field="{}", id="minion1", success="1",
        full_ret='{"success": true, "fun_args": []}',
        alter_time="2020-01-01 00:00:01",
    )
    body = admin_client.get("/api/jobs/{}/summary/".format(jid), **jwt).json()
    # Unknown expected roster is not the same as "nothing missing".
    assert body["expected_known"] is False
    assert body["missing"] == []
    assert body["returned"] == ["minion1"]


@pytest.mark.django_db()
def test_job_summary_route_is_not_shadowed_by_the_detail_route(admin_client, jwt):
    response = admin_client.get("/api/jobs/20200101000000000011/summary/", **jwt)
    assert response.status_code == 200
    assert "published_to" in response.json()


@pytest.mark.django_db()
def test_job_summary_reports_what_was_targeted(admin_client, jwt):
    jid = "20200101000000000012"
    Jids.objects.create(
        jid=jid,
        load='{"user": "admin", "tgt": "G@role:web", "tgt_type": "compound",'
             ' "fun": "state.apply", "arg": ["nginx"],'
             ' "metadata": {"change": "CHG-42"},'
             ' "key": "MASTER-PUBLISH-KEY", "kwargs": {"token": "SECRET-TOKEN"}}',
    )
    body = admin_client.get("/api/jobs/{}/summary/".format(jid), **jwt).json()
    # The returning minion is not the same thing as the target expression.
    assert body["target"] == "G@role:web"
    assert body["target_type"] == "compound"
    assert body["metadata"] == {"change": "CHG-42"}
    # The load also carries the master publish key and sometimes an eauth
    # token; neither may leave the server.
    serialised = str(body)
    assert "MASTER-PUBLISH-KEY" not in serialised
    assert "SECRET-TOKEN" not in serialised
    assert "key" not in body and "kwargs" not in body


def _highstate_return(states):
    return json.dumps({"fun": "state.apply", "fun_args": [], "success": True,
                       "return": states})


@pytest.mark.django_db()
def test_state_durations_aggregates_timing_and_change_rate(admin_client, jwt):
    from django.utils import timezone

    slow = {
        "pkg_|-nginx_|-nginx_|-installed": {
            "result": True, "duration": 30000.0, "changes": {},
            "__sls__": "web.nginx", "__id__": "nginx",
        },
        "file_|-conf_|-/etc/app.conf_|-managed": {
            "result": True, "duration": 50.0, "changes": {"diff": "..."},
            "__sls__": "web.conf", "__id__": "conf",
        },
    }
    for i, minion in enumerate(("minion1", "minion2")):
        SaltReturns.objects.create(
            fun="state.apply", jid="2020010100000000002{}".format(i),
            return_field="{}", id=minion, success="1",
            full_ret=_highstate_return(slow), alter_time=timezone.now(),
        )

    body = admin_client.get("/api/states/durations/?days=7", **jwt).json()
    assert body["highstates"] == 2
    # Ordered by the time they actually cost.
    assert [s["state"] for s in body["states"]] == ["nginx", "conf"]
    nginx = body["states"][0]
    assert nginx["sls"] == "web.nginx"
    assert nginx["runs"] == 2 and nginx["minions"] == 2
    assert nginx["mean_ms"] == 30000.0 and nginx["total_ms"] == 60000.0
    # nginx is converged; conf reports changes on every run.
    assert nginx["change_rate"] == 0.0
    assert body["states"][1]["change_rate"] == 1.0


@pytest.mark.django_db()
def test_state_durations_survives_a_failed_render(admin_client, jwt):
    from django.utils import timezone

    # A render error returns a list of strings where the state map would be.
    SaltReturns.objects.create(
        fun="state.apply", jid="20200101000000000030", return_field="{}",
        id="minion1", success="0",
        full_ret=json.dumps({"return": ["Rendering SLS failed"]}),
        alter_time=timezone.now(),
    )
    body = admin_client.get("/api/states/durations/", **jwt).json()
    assert body["states"] == [] and body["highstates"] == 0


@pytest.mark.django_db()
def test_state_durations_can_scope_to_one_minion(admin_client, jwt):
    from django.utils import timezone

    states = {"pkg_|-a_|-a_|-installed": {
        "result": True, "duration": 10.0, "changes": {}, "__sls__": "s", "__id__": "a"}}
    for minion in ("minion1", "minion2"):
        SaltReturns.objects.create(
            fun="state.apply", jid="2020010100000000004" + minion[-1],
            return_field="{}", id=minion, success="1",
            full_ret=_highstate_return(states), alter_time=timezone.now(),
        )
    body = admin_client.get("/api/states/durations/?id=minion1", **jwt).json()
    assert body["highstates"] == 1
    assert body["states"][0]["minions"] == 1


@pytest.mark.django_db()
def test_state_detail_lists_each_minion(admin_client, jwt):
    from django.utils import timezone

    states = {
        "pkg_|-nginx_|-nginx_|-installed": {
            "result": True, "duration": 30000.0, "changes": {},
            "__sls__": "web.nginx", "__id__": "nginx", "comment": "already installed",
        },
    }
    failed = {
        "pkg_|-nginx_|-nginx_|-installed": {
            "result": False, "duration": 900.0, "changes": {"new": "x"},
            "__sls__": "web.nginx", "__id__": "nginx", "comment": "boom",
        },
    }
    for i, (minion, payload) in enumerate((("minion1", states), ("minion2", failed))):
        SaltReturns.objects.create(
            fun="state.apply", jid="2020010100000000005{}".format(i),
            return_field="{}", id=minion, success="1",
            full_ret=_highstate_return(payload), alter_time=timezone.now(),
        )
    body = admin_client.get("/api/states/durations/?state=nginx", **jwt).json()
    assert body["state"] == "nginx"
    assert [m["minion"] for m in body["minions"]] == ["minion1", "minion2"]
    slow, quick = body["minions"]
    assert slow["duration_ms"] == 30000.0 and slow["result"] is True
    assert quick["result"] is False and quick["changed"] is True
    assert quick["comment"] == "boom"


@pytest.mark.django_db()
def test_state_detail_keeps_only_the_newest_run_per_minion(admin_client, jwt):
    import datetime

    from django.utils import timezone

    now = timezone.now()
    for i, (age, duration) in enumerate(((2, 100.0), (0, 200.0))):
        SaltReturns.objects.create(
            fun="state.apply", jid="2020010100000000006{}".format(i),
            return_field="{}", id="minion1", success="1",
            full_ret=_highstate_return({
                "pkg_|-a_|-a_|-installed": {
                    "result": True, "duration": duration, "changes": {},
                    "__sls__": "s", "__id__": "a"}}),
            alter_time=now - datetime.timedelta(days=age),
        )
    body = admin_client.get("/api/states/durations/?state=a", **jwt).json()
    assert len(body["minions"]) == 1
    assert body["minions"][0]["duration_ms"] == 200.0
