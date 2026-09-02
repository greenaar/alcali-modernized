"""How a job's success is decided, from real returner payloads.

The returner stores `ret.get("success", False)`, so the success column reads
false both when a job failed and when its payload never mentioned success.
Reporting the second case as a failure marks succeeding jobs as failed.
"""
import json

import pytest

from api.models import SaltReturns


def make(full_ret, success_column="0"):
    return SaltReturns(
        fun="state.apply", jid="20260101000000000000", return_field="{}",
        id="minion1", success=success_column, full_ret=json.dumps(full_ret),
        alter_time="2026-01-01 00:00:00",
    )


def test_explicit_success_is_authoritative():
    assert make({"success": True, "return": {}}).success_bool() is True
    assert make({"success": False, "return": {}}, "1").success_bool() is False


def test_a_highstate_is_judged_on_its_state_results():
    states = {
        "pkg_|-a_|-a_|-installed": {"result": True, "changes": {}},
        # A state that needed no changes reports None, which is not a failure.
        "file_|-b_|-b_|-managed": {"result": None, "changes": {}},
    }
    # No top-level success key, and the returner therefore wrote 0.
    assert make({"return": states, "retcode": 0}).success_bool() is True

    states["pkg_|-c_|-c_|-installed"] = {"result": False, "comment": "boom"}
    assert make({"return": states, "retcode": 2}).success_bool() is False


def test_retcode_decides_a_bare_return():
    assert make({"return": "pong", "retcode": 0}).success_bool() is True
    assert make({"return": "error text", "retcode": 1}).success_bool() is False


def test_unknown_is_unknown_rather_than_failed():
    # Nothing in the payload says, and the column's false is the returner's
    # default rather than a verdict.
    assert make({"return": None}).success_bool() is None
    # An affirmative column is still worth something.
    assert make({"return": None}, "1").success_bool() is True


@pytest.mark.django_db()
def test_serializer_reports_unknown_as_null(admin_client, jwt):
    SaltReturns.objects.create(
        fun="custom.thing", jid="20260101000000000001", return_field="{}",
        id="minion1", success="0",
        full_ret=json.dumps({"fun": "custom.thing", "fun_args": [], "return": None}),
        alter_time="2026-01-01 00:00:00",
    )
    row = admin_client.get("/api/jobs/", **jwt).json()[0]
    assert row["success"] is None


@pytest.mark.django_db()
def test_a_succeeding_highstate_is_not_reported_as_failed(admin_client, jwt):
    # The regression this guards: a highstate whose payload carries no success
    # key, so the returner wrote success=0, while every state passed.
    states = {"pkg_|-a_|-a_|-installed": {"result": True, "changes": {}}}
    SaltReturns.objects.create(
        fun="state.apply", jid="20260101000000000002", return_field="{}",
        id="minion1", success="0",
        full_ret=json.dumps({"fun": "state.apply", "fun_args": [],
                             "return": states, "retcode": 0}),
        alter_time="2026-01-01 00:00:00",
    )
    row = admin_client.get("/api/jobs/", **jwt).json()[0]
    assert row["success"] is True
