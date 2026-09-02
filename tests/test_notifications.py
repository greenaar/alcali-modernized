"""Alerting on the two signals the dashboard already computes."""
import datetime
import json
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from api import notifications
from api.models import (
    ConformityCache,
    Keys,
    Minions,
    NotificationRule,
    NotificationState,
    SaltReturns,
)


def rule(**kwargs):
    kwargs.setdefault("name", "r")
    kwargs.setdefault("trigger", NotificationRule.CONFORMITY)
    return NotificationRule.objects.create(**kwargs)


def drifted(minion_id):
    """A minion whose cached verdict is a failed highstate."""
    Minions.objects.create(minion_id=minion_id, grain="{}", pillar="{}")
    SaltReturns.objects.create(
        fun="state.apply", jid="20260902010000000001", return_field="{}",
        id=minion_id, success="1",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": [],
                             "return": {"a_|-a_|-a_|-run": {"result": False}}}),
        alter_time="2026-09-02 01:00:00",
    )


@pytest.mark.django_db()
def test_a_drifted_minion_fires_once_not_every_run():
    """A rule that repeated itself every run would be ignored within a week."""
    drifted("web1")
    r = rule(webhook_url="https://hook.example/x")
    with mock.patch.object(notifications, "_send_webhook") as hook:
        first = notifications.run_rules()
        second = notifications.run_rules()
    assert [e["minion"] for e in first] == ["web1"]
    assert second == []
    assert hook.call_count == 1


@pytest.mark.django_db()
def test_a_recovery_is_reported_too():
    drifted("web1")
    r = rule()
    notifications.run_rules()
    # The minion becomes conformant.
    ConformityCache.objects.update(verdict=True)
    events = notifications.run_rules()
    assert len(events) == 1
    assert events[0]["state"] == NotificationState.CLEAR
    assert events[0]["minion"] == "web1"


@pytest.mark.django_db()
def test_a_dry_run_sends_nothing_and_remembers_nothing():
    drifted("web1")
    rule(webhook_url="https://hook.example/x")
    with mock.patch.object(notifications, "_send_webhook") as hook:
        first = notifications.run_rules(dry_run=True)
        second = notifications.run_rules(dry_run=True)
    hook.assert_not_called()
    assert len(first) == 1 and len(second) == 1
    assert not NotificationState.objects.exists()


@pytest.mark.django_db()
def test_a_disabled_rule_is_not_evaluated():
    drifted("web1")
    rule(enabled=False)
    assert notifications.run_rules() == []


@pytest.mark.django_db()
def test_both_channels_are_used():
    drifted("web1")
    rule(webhook_url="https://hook.example/x", email_to="a@example.com, b@example.com")
    with mock.patch.object(notifications, "_send_webhook") as hook:
        notifications.run_rules()
    hook.assert_called_once()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["a@example.com", "b@example.com"]


@pytest.mark.django_db()
def test_a_failing_webhook_does_not_stop_the_email():
    """The point is that somebody hears about it."""
    drifted("web1")
    rule(webhook_url="https://hook.example/x", email_to="a@example.com")
    with mock.patch.object(notifications, "_send_webhook",
                           side_effect=RuntimeError("connection refused")):
        events = notifications.run_rules()
    assert len(mail.outbox) == 1
    assert "connection refused" in events[0]["errors"][0]


@pytest.mark.django_db()
def test_a_failed_delivery_is_still_recorded():
    """Retrying every run would turn one unreachable endpoint into a flood
    the moment it came back."""
    drifted("web1")
    rule(webhook_url="https://hook.example/x")
    with mock.patch.object(notifications, "_send_webhook",
                           side_effect=RuntimeError("down")):
        notifications.run_rules()
        again = notifications.run_rules()
    assert again == []


@pytest.mark.django_db()
def test_a_rule_that_cannot_be_evaluated_does_not_stop_the_others():
    drifted("web1")
    bad = rule(name="bad")
    good = rule(name="good")
    real = notifications.offenders_for

    def offenders(r):
        if r.pk == bad.pk:
            raise RuntimeError("boom")
        return real(r)

    with mock.patch.object(notifications, "offenders_for", side_effect=offenders):
        events = notifications.run_rules()
    assert any(e.get("error") for e in events)
    assert any(e.get("minion") == "web1" for e in events)


@pytest.mark.django_db()
def test_silence_is_measured_against_the_accepted_keys():
    """A minion that stops answering leaves no row, so returns alone cannot
    find it."""
    Keys.objects.create(minion_id="quiet", status="accepted")
    Keys.objects.create(minion_id="chatty", status="accepted")
    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000002", return_field="{}",
        id="chatty", success="1", full_ret="{}", alter_time=timezone.now(),
    )
    offenders = notifications._silent_offenders(days=1)
    assert "quiet" in offenders
    assert "never returned" in offenders["quiet"]
    assert "chatty" not in offenders


@pytest.mark.django_db()
def test_a_minion_that_returned_long_ago_counts_as_silent():
    Keys.objects.create(minion_id="stale", status="accepted")
    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000003", return_field="{}",
        id="stale", success="1", full_ret="{}",
        alter_time=timezone.now() - datetime.timedelta(days=5),
    )
    assert "stale" in notifications._silent_offenders(days=1)


@pytest.mark.django_db()
def test_an_unaccepted_key_is_not_expected_to_report():
    Keys.objects.create(minion_id="pending", status="pending")
    assert notifications._silent_offenders(days=1) == {}


@pytest.fixture()
def staff_client(django_user_model):
    from rest_framework.test import APIClient

    user = django_user_model.objects.create_user("boss", password="x", is_staff=True)
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.mark.django_db()
def test_rules_are_staff_only(django_user_model):
    from rest_framework.test import APIClient

    django_user_model.objects.create_user("plain", password="x")
    api = APIClient()
    api.force_authenticate(user=django_user_model.objects.get(username="plain"))
    assert api.get("/api/notifications/").status_code == 403


@pytest.mark.django_db()
def test_a_rule_with_nowhere_to_send_is_refused(staff_client):
    """Useless is worse than refused: it looks configured."""
    response = staff_client.post(
        "/api/notifications/", {"name": "nowhere", "trigger": "conformity"}
    )
    assert response.status_code == 400
    assert "webhook" in str(response.json())


@pytest.mark.django_db()
def test_a_rule_with_either_channel_is_accepted(staff_client):
    assert staff_client.post(
        "/api/notifications/",
        {"name": "hook", "trigger": "conformity", "webhook_url": "https://h/x"},
    ).status_code == 201
    assert staff_client.post(
        "/api/notifications/",
        {"name": "mail", "trigger": "silent", "email_to": "a@example.com"},
    ).status_code == 201


@pytest.mark.django_db()
def test_a_test_send_exercises_the_real_channels(staff_client):
    r = rule(email_to="a@example.com")
    response = staff_client.post("/api/notifications/{}/test/".format(r.pk))
    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert len(mail.outbox) == 1
    assert "no minion is affected" in mail.outbox[0].body


@pytest.mark.django_db()
def test_a_test_send_reports_a_broken_channel(staff_client):
    r = rule(webhook_url="https://hook.example/x")
    with mock.patch.object(notifications, "_send_webhook",
                           side_effect=RuntimeError("refused")):
        response = staff_client.post("/api/notifications/{}/test/".format(r.pk))
    assert response.json()["sent"] is False
    assert "refused" in response.json()["errors"][0]


@pytest.mark.django_db()
def test_preview_shows_what_would_fire_without_sending(staff_client):
    drifted("web1")
    rule(webhook_url="https://hook.example/x")
    with mock.patch.object(notifications, "_send_webhook") as hook:
        response = staff_client.post("/api/notifications/preview/")
    hook.assert_not_called()
    assert [e["minion"] for e in response.json()["events"]] == ["web1"]
    assert not NotificationState.objects.exists()
