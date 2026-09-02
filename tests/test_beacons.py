"""Mirroring and managing minion-side beacons."""
import json
from unittest import mock

import pytest
from rest_framework.test import APIClient

from api.backend import netapi
from api.backend.salt_api import SaltApiError
from api.models import AuditLog, Beacon


@pytest.fixture()
def client(django_user_model):
    user = django_user_model.objects.create_user("op", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


LISTED = {
    "web1": {
        "inotify": [{"files": {"/etc/passwd": {}}}, {"enabled": True}],
        "load": [{"averages": {"1m": [0.0, 2.0]}}, {"enabled": False}],
        # The minion-wide switch travels in the same mapping as the beacons.
        "enabled": True,
    },
    # A minion the master could not collect from.
    "web2": False,
}


@pytest.mark.django_db()
def test_refresh_stores_each_beacon_and_skips_the_global_switch():
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.local.return_value = {"return": [LISTED]}
        answered = netapi.refresh_beacons()
    assert set(answered) == {"web1"}
    assert set(Beacon.objects.values_list("name", flat=True)) == {"inotify", "load"}
    assert not Beacon.objects.filter(name="enabled").exists()


@pytest.mark.django_db()
def test_the_enabled_flag_is_read_out_of_the_config():
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.local.return_value = {"return": [LISTED]}
        netapi.refresh_beacons()
    assert Beacon.objects.get(name="inotify").enabled() is True
    assert Beacon.objects.get(name="load").enabled() is False


@pytest.mark.django_db()
def test_a_beacon_with_no_enabled_entry_counts_as_enabled():
    beacon = Beacon.objects.create(
        minion="web1", name="diskusage", config=json.dumps([{"/": "90%"}])
    )
    assert beacon.enabled() is True


@pytest.mark.django_db()
def test_unparseable_config_does_not_raise():
    beacon = Beacon.objects.create(minion="web1", name="broken", config="not json")
    assert beacon.enabled() is True


@pytest.mark.django_db()
def test_a_fleet_that_all_failed_to_answer_is_reported():
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.local.return_value = {"return": [{"a": False, "b": False}]}
        ret = netapi.refresh_beacons()
    assert "none returned their beacons" in ret["error"]


@pytest.mark.django_db()
def test_refresh_replaces_rather_than_accumulates():
    Beacon.objects.create(minion="web1", name="gone", config="[]")
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.local.return_value = {"return": [LISTED]}
        netapi.refresh_beacons()
    assert not Beacon.objects.filter(name="gone").exists()


@pytest.mark.django_db()
def test_an_unreachable_master_is_reported():
    with mock.patch.object(netapi, "api_connect", side_effect=SaltApiError("boom")):
        assert netapi.refresh_beacons() == {"error": "boom"}


@pytest.mark.django_db()
def test_an_unknown_action_is_refused_before_calling_salt():
    with mock.patch.object(netapi, "api_connect") as connect:
        ret = netapi.manage_beacons("destroy", "inotify", "web1")
    assert "unknown action" in ret["error"]
    connect.assert_not_called()


@pytest.mark.django_db()
def test_disabling_a_beacon_rereads_it_from_the_minion():
    """The minion owns this configuration, so the stored copy is refreshed
    rather than patched."""
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.local.side_effect = [
            {"return": [{"web1": {"result": True}}]},
            {"return": [LISTED]},
        ]
        ret = netapi.manage_beacons("disable", "load", "web1")
    assert ret == {"web1": True}
    assert Beacon.objects.filter(minion="web1").count() == 2


@pytest.mark.django_db()
def test_the_api_lists_beacons_with_their_enabled_state(client):
    Beacon.objects.create(
        minion="web1", name="load", config=json.dumps([{"enabled": False}])
    )
    response = client.get("/api/beacons/")
    assert response.status_code == 200
    assert response.json()[0]["enabled"] is False


@pytest.mark.django_db()
def test_managing_a_beacon_requires_every_field(client):
    response = client.post("/api/beacons/manage/", {"action": "disable"})
    assert response.status_code == 400


@pytest.mark.django_db()
def test_managing_a_beacon_is_recorded(client):
    with mock.patch("api.views.alcali.manage_beacons", return_value={"web1": True}):
        response = client.post(
            "/api/beacons/manage/",
            {"action": "disable", "minion": "web1", "name": "load"},
        )
    assert response.status_code == 200
    assert AuditLog.objects.get(action="beacon.disable").target == "web1:load"
