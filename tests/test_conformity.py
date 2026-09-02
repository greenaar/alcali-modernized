"""Which run a minion's conformity is judged on."""
import json

import pytest

from api.models import Minions, SaltReturns


def highstate(minion, jid, result, fun_args=None):
    states = {"pkg_|-a_|-a_|-installed": {"result": result, "changes": {}}}
    return SaltReturns.objects.create(
        fun="state.apply", jid=jid, return_field="{}", id=minion, success="1",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": fun_args or [],
                             "return": states}),
        alter_time="2026-09-0{} 00:00:00".format(jid[-1]),
    )


@pytest.mark.django_db()
def test_conformity_uses_the_most_recent_highstate():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    highstate("m1", "20260901000000000001", False)   # older, failed
    highstate("m1", "20260902000000000002", True)    # newest, passed
    # The window used to be re-sorted oldest-first, so a minion whose latest
    # highstate passed kept reporting the previous failure.
    assert minion.conformity() is True


@pytest.mark.django_db()
def test_conformity_follows_a_new_failure():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    highstate("m1", "20260901000000000001", True)
    highstate("m1", "20260902000000000002", False)
    assert minion.conformity() is False


@pytest.mark.django_db()
def test_a_targeted_state_run_is_not_a_highstate():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    highstate("m1", "20260901000000000001", True)
    # `state.apply users` is a targeted run and says nothing about the whole
    # minion, so it must not displace the highstate before it.
    highstate("m1", "20260902000000000002", False, fun_args=["users"])
    assert minion.conformity() is True


@pytest.mark.django_db()
def test_a_highstate_further_back_is_still_found():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    highstate("m1", "20260901000000000001", True)
    for i in range(2, 6):
        highstate("m1", "2026090200000000000{}".format(i), False, fun_args=["users"])
    # Only the two most recent runs used to be considered, so a run of targeted
    # states left conformity unknown rather than reporting the last highstate.
    assert minion.conformity() is True


@pytest.mark.django_db()
def test_no_highstate_at_all_is_unknown():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    highstate("m1", "20260901000000000001", True, fun_args=["users"])
    assert minion.conformity() is None


@pytest.mark.django_db()
def test_a_state_entry_that_is_not_a_mapping_does_not_crash():
    """A module returning a bare value puts a string here rather than a state
    result, and calling .get on it took the whole minions list down."""
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    SaltReturns.objects.create(
        fun="state.apply", jid="20260901000000000001", return_field="{}",
        id="m1", success="1",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": [],
                             "return": {"odd_|-x_|-x_|-run": "not a mapping"}}),
        alter_time="2026-09-01 00:00:00",
    )
    assert minion.conformity() is False


@pytest.mark.django_db()
def test_a_fully_converged_highstate_is_conformant():
    """537 states, all result true with no changes - the shape of a healthy
    highstate on a real fleet."""
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    states = {
        "file_|-f{0}_|-/etc/f{0}_|-managed".format(i): {
            "result": True, "changes": {}, "comment": "already in the correct state",
            "duration": 2.1, "__sls__": "common", "__id__": "f{}".format(i),
        }
        for i in range(537)
    }
    SaltReturns.objects.create(
        fun="state.apply", jid="20260901000000000001", return_field="{}",
        id="m1", success="1",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": [], "return": states}),
        alter_time="2026-09-01 00:00:00",
    )
    assert minion.conformity() is True


@pytest.mark.django_db()
def test_one_drifted_state_among_many_is_not_conformant():
    minion = Minions.objects.create(minion_id="m1", grain="{}", pillar="{}")
    states = {
        "file_|-f{0}_|-/etc/f{0}_|-managed".format(i): {"result": True, "changes": {}}
        for i in range(100)
    }
    # None: made no changes but would have.
    states["file_|-drift_|-/etc/drift_|-managed"] = {"result": None, "changes": {}}
    SaltReturns.objects.create(
        fun="state.apply", jid="20260901000000000001", return_field="{}",
        id="m1", success="1",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": [], "return": states}),
        alter_time="2026-09-01 00:00:00",
    )
    assert minion.conformity() is False
