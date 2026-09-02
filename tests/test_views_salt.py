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
