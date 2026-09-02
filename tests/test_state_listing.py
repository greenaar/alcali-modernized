"""What the master's file server can apply, as state names."""
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from api.backend import netapi
from api.backend.salt_api import SaltApiError


@pytest.fixture()
def client(django_user_model):
    user = django_user_model.objects.create_user("op", password="x")
    api = APIClient()
    api.force_authenticate(user=user)
    return api


FILES = [
    "top.sls",
    "common/init.sls",
    "common/files.sls",
    "apache/vhosts/ssl.sls",
    "orch/deploy.sls",
    "common/files/motd.jinja",   # not a state
    "README.md",
]


def listed(files):
    with mock.patch.object(netapi, "api_connect") as connect:
        connect.return_value.runner.return_value = {"return": [files]}
        return netapi.list_state_files()


def test_paths_become_state_names():
    assert listed(FILES) == ["apache.vhosts.ssl", "common", "common.files", "orch.deploy"]


def test_init_is_addressed_by_its_directory():
    assert listed(["deep/nested/init.sls"]) == ["deep.nested"]


def test_top_is_not_something_to_apply():
    assert listed(["top.sls"]) == []


def test_non_sls_files_are_ignored():
    assert listed(["a.jinja", "b.conf", "c.sls"]) == ["c"]


def test_duplicates_collapse():
    """A file server with several backends can serve the same path twice."""
    assert listed(["common/init.sls", "common/init.sls"]) == ["common"]


def test_a_non_list_return_is_an_error_not_an_empty_fileserver():
    assert "error" in listed(False)


def test_an_unreachable_master_surfaces_the_error():
    with mock.patch.object(netapi, "api_connect", side_effect=SaltApiError("boom")):
        assert netapi.list_state_files() == {"error": "boom"}


@pytest.mark.django_db()
def test_the_endpoint_passes_the_saltenv_through(client):
    with mock.patch("api.views.alcali.list_state_files", return_value=["a"]) as lister:
        response = client.get(reverse("states-available"), {"saltenv": "dev"})
    lister.assert_called_once_with("dev")
    assert response.json() == {
        "states": ["a"], "saltenv": "dev", "error": None, "unavailable": False,
    }


@pytest.mark.django_db()
def test_an_unreachable_master_leaves_the_field_free_text(client):
    """This fills an autocomplete; it must not block a run."""
    with mock.patch("api.views.alcali.list_state_files",
                    return_value={"error": "no master"}):
        response = client.get(reverse("states-available"))
    assert response.status_code == 200
    assert response.json()["unavailable"] is True
    assert response.json()["states"] == []


@pytest.mark.django_db()
def test_listing_states_requires_authentication():
    assert APIClient().get(reverse("states-available")).status_code in (401, 403)
