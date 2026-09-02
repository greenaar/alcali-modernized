"""Up and down as the master sees it, distinct from last-returned."""
from unittest import mock

import pytest
from rest_framework.test import APIClient

from api.backend import netapi
from api.backend.salt_api import SaltApiError


@pytest.fixture()
def client(django_user_model):
    user = django_user_model.objects.create_user("op", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.mark.django_db()
def test_presence_splits_up_from_down(client):
    with mock.patch("api.views.alcali.minion_presence",
                    return_value={"up": ["a"], "down": ["b"]}):
        response = client.get("/api/minions/presence/")
    assert response.status_code == 200
    assert response.json() == {
        "up": ["a"], "down": ["b"], "error": None, "unavailable": False,
    }


@pytest.mark.django_db()
def test_an_unreachable_master_is_reported(client):
    with mock.patch("api.views.alcali.minion_presence",
                    return_value={"error": "Salt API request failed"}):
        response = client.get("/api/minions/presence/")
    # The minions list works without presence, so this degrades to unknown
    # rather than failing the request.
    assert response.status_code == 200
    assert response.json()["unavailable"] is True
    assert response.json()["up"] == []


@pytest.mark.django_db()
def test_presence_requires_authentication():
    assert APIClient().get("/api/minions/presence/").status_code in (401, 403)


def test_the_lists_are_sorted_and_defaulted():
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.runner.return_value = {"return": [{"up": ["b", "a"]}]}
        assert netapi.minion_presence() == {"up": ["a", "b"], "down": []}


def test_a_non_mapping_status_is_an_error_not_an_empty_fleet():
    """manage.status returning something unexpected must not read as
    'every minion is down'."""
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.runner.return_value = {"return": [False]}
        assert "error" in netapi.minion_presence()


def test_an_unreachable_master_surfaces_the_salt_error():
    with mock.patch.object(netapi, "api_connect", side_effect=SaltApiError("boom")):
        assert netapi.minion_presence() == {"error": "boom"}
