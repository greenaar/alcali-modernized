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
