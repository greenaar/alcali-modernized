"""The overview reports the fleet as the master sees it, not as last refreshed.

Every overview card used to count from Alcali's own snapshot tables, which
changed only when someone pressed refresh on the Keys or Minions page: key
counts lagged the master, the highstate chart only counted inventoried
minions, a new master reported nobody as reporting, and the stream status
flipped to NOT OK whenever the master went quiet for 45 seconds.
"""
import json
import queue
import threading
import time

import pytest

from api.backend import netapi
from api.backend.salt_api import SaltApiError
from api.models import Keys, Minions, SaltReturns, Schedule


def listing(accepted=(), pre=(), rejected=(), denied=()):
    return {
        "minions": list(accepted),
        "minions_pre": list(pre),
        "minions_rejected": list(rejected),
        "minions_denied": list(denied),
    }


class FakeApi:
    """key.list_all and key.finger, counting the calls made."""

    def __init__(self, keys):
        self.keys = keys
        self.calls = []

    def wheel(self, fun, **kwargs):
        self.calls.append(fun)
        if fun == "key.list_all":
            return {"return": [{"data": {"return": self.keys}}]}
        if fun == "key.finger":
            minion = kwargs["match"]
            bucket = next(b for b, ids in self.keys.items() if minion in ids)
            return {"return": [{"data": {"return": {bucket: {minion: "fp-" + minion}}}}]}
        raise AssertionError(fun)


@pytest.fixture
def master(monkeypatch):
    """A master whose key list the test controls; syncs are never throttled."""
    api = FakeApi(listing())
    monkeypatch.setattr(netapi, "api_connect", lambda: api)
    monkeypatch.setattr(netapi, "KEY_SYNC_INTERVAL", 0)
    monkeypatch.setattr("api.views.alcali.sync_keys", lambda: netapi.sync_keys(max_age=0))
    return api


# --- key sync ---------------------------------------------------------------


@pytest.mark.django_db()
def test_sync_keys_mirrors_the_master(master):
    master.keys = listing(accepted=["a", "b"], pre=["c"])
    assert netapi.sync_keys(max_age=0) == {"result": "synced"}
    assert sorted(Keys.objects.values_list("minion_id", "status")) == [
        ("a", "accepted"), ("b", "accepted"), ("c", "unaccepted"),
    ]
    assert Keys.objects.get(minion_id="a").pub == "fp-a"


@pytest.mark.django_db()
def test_sync_keys_fetches_fingerprints_only_for_new_keys(master):
    master.keys = listing(accepted=["a", "b"])
    netapi.sync_keys(max_age=0)
    master.calls.clear()
    master.keys = listing(accepted=["a", "b", "c"])
    netapi.sync_keys(max_age=0)
    # One listing and one fingerprint, not one fingerprint per key.
    assert master.calls == ["key.list_all", "key.finger"]


@pytest.mark.django_db()
def test_sync_keys_removes_keys_the_master_no_longer_has(master):
    master.keys = listing(accepted=["a", "b"])
    netapi.sync_keys(max_age=0)
    master.keys = listing(accepted=["a"], rejected=["b"])
    netapi.sync_keys(max_age=0)
    assert sorted(Keys.objects.values_list("minion_id", "status")) == [
        ("a", "accepted"), ("b", "rejected"),
    ]


@pytest.mark.django_db()
def test_sync_keys_drops_schedules_of_minions_whose_key_is_gone(master):
    Schedule.objects.create(minion="a", name="highstate", job="{}")
    Schedule.objects.create(minion="gone", name="highstate", job="{}")
    master.keys = listing(accepted=["a"])
    netapi.sync_keys(max_age=0)
    assert list(Schedule.objects.values_list("minion", flat=True)) == ["a"]


@pytest.mark.django_db()
def test_a_partial_key_listing_changes_nothing(master):
    master.keys = listing(accepted=["a"])
    netapi.sync_keys(max_age=0)
    # Missing buckets would otherwise read as "no keys there" and delete them.
    master.keys = {"minions": []}
    assert "error" in netapi.sync_keys(max_age=0)
    assert list(Keys.objects.values_list("minion_id", flat=True)) == ["a"]


@pytest.mark.django_db()
def test_an_unreachable_master_leaves_the_stored_keys(monkeypatch):
    Keys.objects.create(minion_id="a", status="accepted", pub="")

    def boom():
        raise SaltApiError("connection refused")

    monkeypatch.setattr(netapi, "api_connect", boom)
    assert "error" in netapi.sync_keys(max_age=0)
    assert Keys.objects.count() == 1


@pytest.mark.django_db()
def test_sync_keys_is_throttled(master):
    master.keys = listing(accepted=["a"])
    netapi.sync_keys(max_age=0)
    master.calls.clear()
    assert netapi.sync_keys(max_age=60) == {"result": "fresh"}
    assert master.calls == []


# --- the overview cards -------------------------------------------------------


@pytest.mark.django_db()
def test_keys_status_counts_the_masters_keys(master, admin_client, jwt):
    Keys.objects.create(minion_id="stale", status="accepted", pub="")
    master.keys = listing(accepted=["a", "b", "c"], pre=["d"])
    body = admin_client.get("/api/keys/keys_status/", **jwt).json()
    assert body == {"accepted": 3, "rejected": 0, "denied": 0, "unaccepted": 1}


@pytest.mark.django_db()
def test_a_new_master_reports_its_minions_as_reporting(master, admin_client, jwt):
    from django.utils import timezone

    # Nobody has pressed refresh, so salt_keys is empty - which used to make
    # the overview report no accepted minions while the jobs page showed them
    # returning.
    master.keys = listing(accepted=["salt.aws.example"])
    SaltReturns.objects.create(
        fun="test.ping", jid="20260101000000000001", return_field="true",
        id="salt.aws.example", success="1", full_ret='{"fun_args": []}',
        alter_time=timezone.now(),
    )
    body = admin_client.get("/api/minions/silent/?days=1", **jwt).json()
    assert body["accepted"] == 1
    assert body["silent"] == []


def _highstate(minion, jid, result):
    SaltReturns.objects.create(
        fun="state.apply", jid=jid, return_field="{}", id=minion, success="1",
        full_ret=json.dumps({"fun_args": [], "retcode": 0 if result else 2,
                             "return": {"pkg_|-a_|-a_|-installed": {"result": result}}}),
        alter_time="2026-09-01 00:00:00",
    )


@pytest.mark.django_db()
def test_the_highstate_chart_counts_every_accepted_minion(master, admin_client, jwt):
    master.keys = listing(accepted=["inventoried", "new", "never-ran"])
    Minions.objects.create(minion_id="inventoried", grain="{}", pillar="{}")
    # A decommissioned minion still in the inventory is not part of the fleet.
    Minions.objects.create(minion_id="decommissioned", grain="{}", pillar="{}")
    _highstate("inventoried", "20260901000000000001", True)
    _highstate("new", "20260901000000000002", False)
    _highstate("decommissioned", "20260901000000000003", False)

    body = admin_client.get("/api/minions/conformity/", **jwt).json()
    assert body["name"][0] == "HIGHSTATE"
    assert body["data"][0] == {"conform": 1, "conflict": 1, "unknown": 1}


@pytest.mark.django_db()
def test_stats_do_not_count_schedules_of_departed_minions(master, admin_client, jwt):
    master.keys = listing(accepted=["a"])
    Schedule.objects.create(minion="a", name="highstate", job="{}")
    Schedule.objects.create(minion="gone", name="highstate", job="{}")
    body = admin_client.get("/api/stats/", **jwt).json()
    assert body["schedules"] == 1


# --- the event stream ---------------------------------------------------------


def _drain(gen, count):
    return [next(gen) for _ in range(count)]


def test_a_quiet_stream_gets_keepalives():
    from api.views.alcali import with_keepalive

    upstream = queue.Queue()

    def stream():
        while True:
            item = upstream.get()
            if item is None:
                return
            yield item

    gen = with_keepalive(stream(), interval=0.05)
    upstream.put(b"retry: 400\n\n")
    assert next(gen) == b"retry: 400\n\n"
    # Nothing from the master: a comment line keeps the client from giving up.
    assert next(gen) == b": keepalive\n\n"
    upstream.put(b"data: {}\n\n")
    out = _drain(gen, 1)
    while out[-1] == b": keepalive\n\n":
        out = _drain(gen, 1)
    assert out[-1] == b"data: {}\n\n"
    upstream.put(None)
    assert list(gen) in ([], [b": keepalive\n\n"])


def test_no_keepalive_is_sent_inside_an_event():
    from api.views.alcali import with_keepalive

    release = threading.Event()

    def stream():
        yield b"tag: salt/job/1/new\n"   # half an event
        release.wait(1)
        yield b"data: {}\n\n"

    gen = with_keepalive(stream(), interval=0.05)
    first = next(gen)
    started = time.monotonic()
    release_timer = threading.Timer(0.3, release.set)
    release_timer.start()
    second = next(gen)
    # Waited for the rest of the event rather than splitting it with a comment.
    assert first == b"tag: salt/job/1/new\n"
    assert second == b"data: {}\n\n"
    assert time.monotonic() - started >= 0.2


def test_closing_the_response_closes_the_upstream():
    from api.views.alcali import with_keepalive

    class Upstream:
        closed = False

        def __iter__(self):
            yield b"retry: 400\n\n"
            while not self.closed:
                time.sleep(0.01)

        def close(self):
            self.closed = True

    upstream = Upstream()
    gen = with_keepalive(upstream, interval=0.05)
    next(gen)
    gen.close()   # what Django does when the client goes away
    assert upstream.closed
