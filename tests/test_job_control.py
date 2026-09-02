"""Seeing and stopping a job that is still running."""
import json
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import AuditLog, Jids


@pytest.fixture()
def client(django_user_model):
    user = django_user_model.objects.create_user("op", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


ACTIVE = {
    "20260902010000000000": {
        "Function": "state.apply",
        "Arguments": [],
        "Target": "web*",
        "User": "alice",
        "Running": [{"web1": 1234}, {"web2": 1235}],
        "StartTime": "2026, Sep 02 01:00:00.000000",
    }
}


@pytest.mark.django_db()
def test_active_jobs_are_listed(client):
    with mock.patch("api.views.salt.salt_active_jobs", return_value=ACTIVE):
        response = client.get(reverse("jobs-active"))
    assert response.status_code == 200
    assert response.json() == [
        {
            "jid": "20260902010000000000",
            "fun": "state.apply",
            "arguments": [],
            "target": "web*",
            "user": "alice",
            "running": [{"web1": 1234}, {"web2": 1235}],
            "minions": 2,
            "start": "2026, Sep 02 01:00:00.000000",
        }
    ]


@pytest.mark.django_db()
def test_an_unreachable_master_is_reported_not_an_empty_list(client):
    with mock.patch("api.views.salt.salt_active_jobs",
                    return_value={"error": "Salt API request failed"}):
        response = client.get(reverse("jobs-active"))
    assert response.status_code == 502
    assert "Salt API request failed" in response.json()["error"]


@pytest.mark.django_db()
def test_a_minion_that_is_not_a_mapping_is_skipped(client):
    """jobs.active reports a minion it could not reach as False, the same way
    the schedule runner does."""
    with mock.patch("api.views.salt.salt_active_jobs",
                    return_value=dict(ACTIVE, **{"2026090201": False})):
        response = client.get(reverse("jobs-active"))
    assert response.status_code == 200
    assert [job["jid"] for job in response.json()] == ["20260902010000000000"]


@pytest.mark.django_db()
def test_stopping_a_job_aims_at_the_target_it_was_published_to(client):
    """A stop should not be a broadcast to machines that never ran it."""
    Jids.objects.create(
        jid="20260902010000000000",
        load=json.dumps({"tgt": "web*", "tgt_type": "glob", "fun": "state.apply"}),
    )
    with mock.patch("api.views.salt.salt_kill_job",
                    return_value={"web1": True, "web2": False}) as kill:
        response = client.post(
            reverse("jobs-kill", args=["20260902010000000000"]), {"signal": "term"}
        )
    assert response.status_code == 200
    kill.assert_called_once_with("20260902010000000000", "web*", "glob", "term")
    assert response.json()["stopped"] == ["web1"]


@pytest.mark.django_db()
def test_stopping_an_unknown_job_falls_back_to_every_minion(client):
    with mock.patch("api.views.salt.salt_kill_job", return_value={}) as kill:
        client.post(reverse("jobs-kill", args=["20260902019999999999"]))
    kill.assert_called_once_with("20260902019999999999", "*", "glob", "term")


@pytest.mark.django_db()
def test_an_unknown_signal_is_refused(client):
    with mock.patch("api.views.salt.salt_kill_job") as kill:
        response = client.post(
            reverse("jobs-kill", args=["20260902010000000000"]), {"signal": "shutdown"}
        )
    assert response.status_code == 400
    kill.assert_not_called()


@pytest.mark.django_db()
def test_stopping_a_job_is_recorded(client):
    with mock.patch("api.views.salt.salt_kill_job", return_value={"web1": True}):
        client.post(reverse("jobs-kill", args=["20260902010000000000"]),
                    {"signal": "kill"})
    entry = AuditLog.objects.get(action="job.kill")
    assert entry.target == "20260902010000000000"
    assert "kill" in entry.detail
