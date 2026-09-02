"""The checks that answer "why is this page empty?"."""
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from api import diagnostics
from api.backend.salt_api import SaltApiError
from api.models import Jids, SaltReturns


def status_of(checks, key):
    return next(c["status"] for c in checks if c["key"] == key)


@pytest.fixture()
def staff(django_user_model):
    user = django_user_model.objects.create_user("boss", password="x", is_staff=True)
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.mark.django_db()
def test_diagnostics_are_staff_only(django_user_model):
    django_user_model.objects.create_user("plain", password="x")
    api = APIClient()
    api.force_authenticate(user=django_user_model.objects.get(username="plain"))
    assert api.get(reverse("diagnostics")).status_code == 403


@pytest.mark.django_db()
def test_a_run_where_every_minion_is_false_is_a_collection_failure():
    """The failure that reads as minions answering no, and is not."""
    check = diagnostics._return_collection_check(
        {"return": [{"a": False, "b": False, "c": False}]}
    )
    assert check["status"] == diagnostics.FAIL
    assert "could not collect" in check["hint"]
    assert "jobs.lookup_jid" in check["hint"]


@pytest.mark.django_db()
def test_a_run_with_real_answers_passes():
    check = diagnostics._return_collection_check({"return": [{"a": True, "b": False}]})
    assert check["status"] == diagnostics.OK


@pytest.mark.django_db()
def test_no_minions_matched_is_unknown_not_a_failure():
    check = diagnostics._return_collection_check({"return": [{}]})
    assert check["status"] == diagnostics.UNKNOWN


@pytest.mark.django_db()
def test_a_return_without_a_matching_jid_row_is_a_job_cache_failure():
    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000000", return_field="{}", id="a",
        success="1", full_ret="{}", alter_time="2026-09-02 01:00:00",
    )
    checks = diagnostics.job_cache_checks()
    assert status_of(checks, "cache.job") == diagnostics.FAIL


@pytest.mark.django_db()
def test_a_job_cache_that_is_keeping_up_passes():
    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000000", return_field="{}", id="a",
        success="1", full_ret="{}", alter_time="2026-09-02 01:00:00",
    )
    Jids.objects.create(jid="20260902010000000000", load="{}")
    checks = diagnostics.job_cache_checks()
    assert status_of(checks, "cache.job") == diagnostics.OK


@pytest.mark.django_db()
def test_an_empty_returner_is_unknown_rather_than_broken():
    checks = diagnostics.job_cache_checks()
    assert status_of(checks, "cache.job") == diagnostics.UNKNOWN


@pytest.mark.django_db()
def test_an_empty_alcali_cache_says_what_fills_it():
    checks = diagnostics.cache_checks()
    minions = next(c for c in checks if c["key"] == "cache.minions")
    assert minions["status"] == diagnostics.WARN
    assert "refresh" in minions["hint"]


@pytest.mark.django_db()
def test_a_user_with_no_settings_fails_before_any_request():
    """Saving an empty token regenerates it, so the reachable case is a user
    carrying no settings row at all."""
    user = mock.Mock(username="nokey", user_settings=None)
    with mock.patch.object(diagnostics, "_salt_client") as client:
        checks = diagnostics.salt_checks(user)
    client.assert_not_called()
    assert status_of(checks, "salt.login") == diagnostics.FAIL


@pytest.mark.django_db()
def test_a_revoked_token_is_named_as_such():
    user = mock.Mock(username="u")
    user.user_settings.token = "REVOKED"
    with mock.patch.object(diagnostics, "_salt_client") as client:
        checks = diagnostics.salt_checks(user)
    client.assert_not_called()
    assert "revoked" in next(
        c["detail"] for c in checks if c["key"] == "salt.login"
    )


@pytest.mark.django_db()
def test_a_401_from_the_master_explains_the_eauth_block(django_user_model):
    user = django_user_model.objects.create_user("u", password="x")
    user.user_settings.token = "tok"
    user.user_settings.save()
    with mock.patch.object(diagnostics, "_salt_client",
                           side_effect=SaltApiError("401 Client Error")):
        checks = diagnostics.salt_checks(user)
    login = next(c for c in checks if c["key"] == "salt.login")
    assert login["status"] == diagnostics.FAIL
    assert "external_auth" in login["hint"]


@pytest.mark.django_db()
def test_a_disabled_client_names_netapi_enable_clients(django_user_model):
    user = django_user_model.objects.create_user("u", password="x")
    user.user_settings.token = "tok"
    user.user_settings.save()
    api = mock.Mock()
    api.wheel.side_effect = SaltApiError("Client disabled")
    api.runner.return_value = {"return": [{"up": [], "down": []}]}
    api.local.return_value = {"return": [{"a": True}]}
    with mock.patch.object(diagnostics, "_salt_client",
                           return_value=(api, "https://s:8080", "rest")):
        checks = diagnostics.salt_checks(user)
    wheel = next(c for c in checks if c["key"] == "salt.wheel")
    assert wheel["status"] == diagnostics.FAIL
    assert "netapi_enable_clients" in wheel["hint"]
    # One client failing must not stop the others being reported.
    assert status_of(checks, "salt.runner") == diagnostics.OK
    assert status_of(checks, "salt.local") == diagnostics.OK


@pytest.mark.django_db()
def test_a_check_that_raises_does_not_take_the_page_down(staff):
    with mock.patch.object(diagnostics, "job_cache_checks",
                           side_effect=RuntimeError("boom")):
        response = staff.get(reverse("diagnostics"))
    assert response.status_code == 200
    assert any(c["status"] == diagnostics.UNKNOWN
               for c in response.json()["checks"])


@pytest.mark.django_db()
def test_the_overall_status_is_the_worst_check(staff):
    with mock.patch.object(diagnostics, "collect", return_value=[
        {"key": "a", "label": "a", "status": diagnostics.OK, "detail": "", "hint": ""},
        {"key": "b", "label": "b", "status": diagnostics.FAIL, "detail": "", "hint": ""},
    ]):
        response = staff.get(reverse("diagnostics"))
    assert response.json()["status"] == diagnostics.FAIL
