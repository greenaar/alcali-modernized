import json
from unittest import mock

import pytest

from api.backend.salt_api import SaltApiClient, SaltApiError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self.payload


def test_login_stores_token_and_low_posts_lowstate(monkeypatch):
    client = SaltApiClient("https://salt.example.test:8080")
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/login"):
            return FakeResponse({"return": [{"token": "abc", "perms": ["test.*"]}]})
        return FakeResponse({"return": [{"minion": True}]})

    monkeypatch.setattr(client.session, "request", request)

    login = client.login("alice", "secret", "rest")
    result = client.local("minion", "test.ping")

    assert login["perms"] == ["test.*"]
    assert client.session.headers["X-Auth-Token"] == "abc"
    assert result == {"return": [{"minion": True}]}
    assert calls[1][2]["json"] == [
        {"client": "local", "tgt": "minion", "fun": "test.ping"}
    ]


def test_tls_verification_is_on_by_default(monkeypatch):
    monkeypatch.delenv("SALT_VERIFY_TLS", raising=False)
    monkeypatch.delenv("SALT_CA_BUNDLE", raising=False)
    assert SaltApiClient("https://salt.example.test").verify is True


def test_invalid_login_response_is_rejected(monkeypatch):
    client = SaltApiClient("https://salt.example.test")
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *args, **kwargs: FakeResponse({"return": [{}]}),
    )
    with pytest.raises(SaltApiError, match="did not contain a token"):
        client.login("alice", "secret", "rest")


def test_an_error_carries_what_salt_said():
    """A bare "500 Server Error" says nothing about which of the several
    possible causes it was, and salt-api puts that in the body."""
    import requests

    from api.backend.salt_api import SaltApiClient, SaltApiError

    class Boom(requests.Response):
        def __init__(self):
            super().__init__()
            self.status_code = 500
            self._content = b'{"return": "Function test.ping is unavailable"}'
            self.url = "https://127.0.0.1:8080/"

    client = SaltApiClient("https://127.0.0.1:8080")
    with mock.patch.object(
        client.session, "request", side_effect=requests.HTTPError(
            "500 Server Error: Internal Server Error", response=Boom()
        )
    ):
        with pytest.raises(SaltApiError) as raised:
            client.low({"client": "runner", "fun": "test.ping"})
    message = str(raised.value)
    assert "500 Server Error" in message
    assert "Function test.ping is unavailable" in message


@pytest.mark.django_db()
def test_cache_refresh_stores_what_the_master_holds(monkeypatch):
    """cache.grains is a runner, so it needs no minion to answer and does not
    go through the job cache the local client reads back."""
    from api.backend import netapi
    from api.models import Minions

    class FakeApi:
        def runner(self, fun, **kwargs):
            if fun == "cache.grains":
                return {"return": [{"web01": {"os": "Ubuntu"}, "gone": {}}]}
            return {"return": [{"web01": {"role": "web"}}]}

    monkeypatch.setattr(netapi, "api_connect", lambda: FakeApi())
    result = netapi.refresh_minions_from_cache()
    assert result["refreshed"] == ["web01"]          # the empty one is skipped
    stored = Minions.objects.get(minion_id="web01")
    assert json.loads(stored.grain)["os"] == "Ubuntu"
    assert json.loads(stored.pillar)["role"] == "web"


@pytest.mark.django_db()
def test_cache_refresh_reports_a_salt_failure(monkeypatch):
    from api.backend import netapi
    from api.backend.salt_api import SaltApiError

    def boom():
        raise SaltApiError("Salt API request failed: connection refused")

    monkeypatch.setattr(netapi, "api_connect", boom)
    assert "connection refused" in netapi.refresh_minions_from_cache()["error"]
