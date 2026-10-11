"""The salt-api token cache.

Every view that touches Salt goes through `api_connect()`, and some of them
loop over the fleet, so a login per call is the difference between one
authentication and one per minion. With the `rest` eauth backend each login
also makes the master call Alcali back to verify the credential, which is why
this is worth a cache rather than being left to the master.
"""

import time
from unittest import mock

import pytest

from api.backend import netapi


class FakeClient:
    """Just enough SaltApiClient to count logins."""

    def __init__(self, expire=None, token="tok-1"):
        self.logins = []
        self.tokens_used = []
        self.reauth = None
        self._expire = expire
        self._token = token

    def login(self, username, credential, eauth):
        self.logins.append((username, credential, eauth))
        expire = self._expire if self._expire is not None else time.time() + 3600
        return {
            "token": "{}-{}".format(self._token, len(self.logins)),
            "expire": expire,
            "perms": [".*"],
        }

    def use_token(self, token):
        self.tokens_used.append(token)


@pytest.fixture(autouse=True)
def _empty_cache():
    netapi._TOKEN_CACHE.clear()
    yield
    netapi._TOKEN_CACHE.clear()


def test_a_second_call_reuses_the_token_instead_of_logging_in():
    client = FakeClient()
    first = netapi._login(client, "alice", "salt-token", "rest")

    held = netapi._cached_entry("alice", "salt-token", "rest")

    assert held == first
    assert len(client.logins) == 1


def test_a_different_credential_does_not_hit_the_same_entry():
    """Regenerating someone's Salt token must not leave the old session usable."""
    client = FakeClient()
    netapi._login(client, "alice", "old-token", "rest")

    assert netapi._cached_entry("alice", "new-token", "rest") is None


def test_a_different_eauth_backend_is_a_different_entry():
    client = FakeClient()
    netapi._login(client, "alice", "salt-token", "rest")

    assert netapi._cached_entry("alice", "salt-token", "pam") is None


def test_an_expired_token_is_not_served():
    client = FakeClient(expire=time.time() + 5)

    netapi._login(client, "alice", "salt-token", "rest")

    # Inside the safety margin, so it is treated as spent before the master
    # does and the caller logs in again rather than racing the expiry.
    assert netapi._cached_entry("alice", "salt-token", "rest") is None


def test_a_login_without_an_expiry_still_caches():
    client = FakeClient(expire="not a number")

    entry = netapi._login(client, "alice", "salt-token", "rest")

    assert entry["expire"] > time.time()
    assert netapi._cached_entry("alice", "salt-token", "rest") is not None


def test_forgetting_a_token_forces_the_next_login():
    client = FakeClient()
    netapi._login(client, "alice", "salt-token", "rest")

    netapi.forget_salt_token("alice", "salt-token", "rest")

    assert netapi._cached_entry("alice", "salt-token", "rest") is None


def test_spent_entries_are_cleared_when_another_is_stored():
    """A regenerated token would otherwise leave its entry behind forever."""
    netapi._login(FakeClient(expire=time.time() + 5), "alice", "old-token", "rest")
    assert len(netapi._TOKEN_CACHE) == 1

    netapi._login(FakeClient(), "alice", "new-token", "rest")

    assert len(netapi._TOKEN_CACHE) == 1


def test_the_cache_can_be_turned_off():
    client = FakeClient()
    with mock.patch.dict("os.environ", {"SALT_TOKEN_CACHE": "false"}):
        netapi._login(client, "alice", "salt-token", "rest")

        assert netapi._cached_entry("alice", "salt-token", "rest") is None
    assert netapi._TOKEN_CACHE == {}
