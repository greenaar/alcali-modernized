import pytest
from api.models import SaltReturns, SaltEvents


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
