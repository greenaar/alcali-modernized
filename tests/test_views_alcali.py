import datetime
import os

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from api.models import (
    Keys,
    Minions,
    SaltReturns,
    MinionsCustomFields,
    Schedule,
    UserSettings,
)


@pytest.mark.django_db()
def test_index(admin_client):
    response = admin_client.get(reverse("index"))
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.parametrize(
    "path",
    ["/login", "/minions", "/minions/minion1", "/jobs/20200101000000000000/minion1"],
)
def test_spa_routes_serve_the_shell(admin_client, path):
    # The frontend routes on the History API: a refresh or a direct link to one
    # of its routes has to return index.html, not a 404.
    response = admin_client.get(path)
    assert response.status_code == 200


@pytest.mark.django_db()
def test_unknown_api_route_still_404s(admin_client, jwt):
    # The catch-all must not swallow the API namespace.
    response = admin_client.get("/api/does-not-exist/", **jwt)
    assert response.status_code == 404


@pytest.mark.django_db()
def test_keys_list(key, admin_client, jwt):
    response = admin_client.get("/api/keys/", **jwt)
    assert len(response.json()) == Keys.objects.count()
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_keys_refresh(key, admin_client, jwt):
    response = admin_client.post("/api/keys/refresh/", {}, **jwt)
    assert response.json()["result"] == "refreshed"
    assert response.status_code == 200


@pytest.mark.django_db()
def test_keys_status(key, admin_client, jwt):
    response = admin_client.get("/api/keys/keys_status/", **jwt)
    assert "accepted" in response.json()
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_keys_manage(key, admin_client, jwt):
    response = admin_client.post(
        "/api/keys/manage_keys/", {"target": "master", "action": "reject"}, **jwt
    )
    assert "result" in response.json()
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_list(minion, admin_client, jwt):
    response = admin_client.get("/api/minions/", **jwt)
    assert response.json()[0]["minion_id"] == "2e220fd40bc5"
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_delete(minion, admin_client, jwt):
    response = admin_client.delete("/api/minions/{}/".format(minion.minion_id), **jwt)
    assert response.status_code == 204


@pytest.mark.django_db()
@pytest.mark.integration
def test_minions_refresh(minion, admin_client, jwt):
    response = admin_client.post(
        "/api/minions/refresh_minions/", {"minion_id": minion.minion_id}, **jwt
    )
    assert "result" in response.json()
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity(minion, admin_client, jwt):
    response = admin_client.get("/api/minions/conformity/", **jwt)
    assert "HIGHSTATE" in response.json()["name"]
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity_change(minion, highstate_diff, admin_client, jwt):
    response = admin_client.get("/api/minions/conformity/", **jwt)
    assert "HIGHSTATE" in response.json()["name"]
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity_detail(minion, highstate, admin_client, jwt):
    highstate()
    response = admin_client.get(
        "/api/minions/{}/conformity_detail/".format(minion.minion_id), **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity_detail_highstate(minion, highstate_diff, admin_client, jwt):
    response = admin_client.get(
        "/api/minions/{}/conformity_detail/".format(minion.minion_id), **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity_detail_empty(minion_master, admin_client, jwt):
    response = admin_client.get(
        "/api/minions/{}/conformity_detail/".format(minion_master.minion_id), **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minions_conformity_render(minion, highstate, minion_master, admin_client, jwt):
    highstate()
    response = admin_client.get("/api/conformity/render/", **jwt)
    assert "name" in response.json()
    assert response.status_code == 200


@pytest.mark.django_db()
def test_minion_field_delete(admin_client, jwt):
    response = admin_client.post(
        "/api/minionsfields/",
        {"name": "highstate", "function": "state.show_highstate", "value": "{}"},
        **jwt
    )
    assert response.status_code == 201

    response = admin_client.post(
        "/api/minionsfields/delete_field/", {"name": "highstate"}, **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_schedules_list(schedule, admin_client, jwt):
    response = admin_client.get("/api/schedules/", **jwt)
    assert response.json()[0]["minion"] == "master"
    assert response.json()[0]["name"] == "job2"
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_schedules_refresh(admin_client, jwt):
    response = admin_client.post("/api/schedules/refresh/", {}, **jwt)
    assert "result" in response.json()
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_schedules_manage(admin_client, jwt):
    response = admin_client.post(
        "/api/run/",
        {
            "command": "salt master schedule.add job2 function='test.ping' seconds=3600",
            "raw": True,
        },
        **jwt
    )
    assert response.status_code == 200
    response = admin_client.post("/api/schedules/refresh/", {}, **jwt)
    assert response.status_code == 200
    response = admin_client.post(
        "/api/schedules/manage/",
        {"action": "delete", "name": "job2", "minion": "master"},
        **jwt
    )
    assert "result" in response.json()
    assert response.status_code == 200


def test_users_create(admin_client, admin_user, dummy_user, jwt):
    # Should successfully create user.
    user = {"username": "foo", "email": "foo@example.com", "password": "not_so_good"}
    response = admin_client.post("/api/users/", user, **jwt)
    assert response.status_code == 201


def test_users_create_json(admin_client, admin_user, jwt):
    # The frontend sends JSON, which omits every field the form left empty.
    user = {"username": "jsonfoo", "email": "jsonfoo@example.com", "password": "not_so_good"}
    response = admin_client.post(
        "/api/users/", user, content_type="application/json", **jwt
    )
    assert response.status_code == 201
    created = User.objects.get(username="jsonfoo")
    assert created.check_password("not_so_good")
    assert created.is_active is True


def test_users_update(admin_client, admin_user, dummy_user, jwt):
    # Should successfully update user.
    user = {"username": "foo", "email": "foo@example.com", "password": "not_so_good"}
    response = admin_client.post("/api/users/", user, **jwt)
    user_id = response.json()["id"]
    assert response.status_code == 201
    user = {"username": "foo", "email": "foo@example.com", "first_name": "bar"}
    response = admin_client.patch(
        "/api/users/{id}/".format(id=user_id),
        user,
        content_type="application/json",
        **jwt
    )
    assert response.status_code == 200


def test_users_list(admin_client, admin_user, dummy_user, jwt):
    # Should return all users.
    response = admin_client.get("/api/users/", **jwt)
    assert response.json()[0]["id"] == admin_user.id
    assert len(response.json()) > 1
    assert response.status_code == 200


def test_dummy_users_list(dummy_client, admin_user, dummy_user, jwt_dummy_user):
    # Should only return current user.
    response = dummy_client.get("/api/users/", **jwt_dummy_user)
    assert response.json()[0]["id"] == dummy_user.id
    assert len(response.json()) == 1
    assert response.status_code == 200


def test_users_refresh_token(admin_client, admin_user, jwt):
    current_token = admin_user.user_settings.token
    response = admin_client.post(
        "/api/users/{}/manage_token/".format(admin_user.id), {"action": "renew"}, **jwt
    )
    assert response.status_code == 200
    assert UserSettings.objects.get(user=admin_user).token != current_token


def test_users_revoke_token(admin_client, admin_user, jwt):
    response = admin_client.post(
        "/api/users/{}/manage_token/".format(admin_user.id), {"action": "revoke"}, **jwt
    )
    assert response.status_code == 200
    assert UserSettings.objects.get(user=admin_user).token == "REVOKED"


def test_jobs_graph(admin_client, jwt):
    response = admin_client.get("/api/jobs/graph?period=2", **jwt)
    assert "labels" in response.json()
    assert response.status_code == 200


def test_jobs_graph_highstate(admin_client, jwt):
    response = admin_client.get("/api/jobs/graph?period=2&fun=highstate", **jwt)
    assert "labels" in response.json()
    assert response.status_code == 200


def test_graph_other_filter(admin_client, highstate, dummy_state, jwt):
    highstate()
    response = admin_client.get("/api/jobs/graph?period=0&fun=other", **jwt)
    assert response.status_code == 200
    assert response.json()["series"][0][0] >= 1


def test_stats(admin_client, jwt):
    response = admin_client.get("/api/stats/", **jwt)
    for i in ["jobs", "events", "schedules"]:
        assert i in response.json()
    assert response.status_code == 200


def test_get_events(admin_client, jwt):
    response = admin_client.get("/api/event_stream/", **jwt)
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_run_scheduled_cron(admin_client, jwt):
    response = admin_client.post(
        "/api/run/",
        {
            "raw": "true",
            "command": "salt * test.ping",
            "schedule": "true",
            "schedule_type": "cron",
            "cron": "* * * * *",
        },
        **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_run_scheduled_once(admin_client, jwt):
    response = admin_client.post(
        "/api/run/",
        {
            "raw": "true",
            "command": "salt * test.ping",
            "schedule": "{}".format(
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ),
            "schedule_type": "once",
        },
        **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_get_functions(admin_client, jwt):
    response = admin_client.get("/api/functions/", **jwt)
    assert response.status_code == 200


@pytest.mark.django_db()
@pytest.mark.integration
def test_wheel_raw(admin_client, jwt):
    response = admin_client.post(
        "/api/run/",
        {"command": "salt --client=runner pillar.show_top", "raw": True},
        **jwt
    )
    assert response.status_code == 200


@pytest.mark.django_db()
def test_search_minion(admin_client, dummy_state, minion_master, jwt):
    response = admin_client.get("/api/search/?q=master", **jwt)
    assert response.json()["query"] == "master"
    assert response.json()["minions"][0]["minion_id"] == "master"


@pytest.mark.django_db()
def test_search_job(admin_client, dummy_state, dummy_jid, minion_master, jwt):
    response = admin_client.get("/api/search/?q=20190507190955945844", **jwt)
    assert response.json()["query"] == "20190507190955945844"
    assert response.json()["jobs"][0]["jid"] == dummy_state.jid


@pytest.mark.django_db()
def test_verify_token(admin_client, admin_user, jwt):
    """Salt expects a list of ACL permissions"""
    response = admin_client.post(
        "/api/token/verify/",
        {"username": admin_user.username, "password": admin_user.user_settings.token},
        **jwt
    )
    assert isinstance(response.json(), list)

    response = admin_client.post(
        "/api/token/verify/",
        {"username": "wrong_username", "password": admin_user.user_settings.token},
        **jwt
    )
    assert response.status_code == 401

    response = admin_client.post(
        "/api/token/verify/",
        {"username": admin_user.username, "password": "wrong_password"},
        **jwt
    )
    assert response.status_code == 401


# --- authorization -------------------------------------------------------
#
# Every viewset below used to run on the project-wide IsAuthenticated default,
# so any signed-in account could reach records that are not its own.


@pytest.mark.django_db()
def test_user_settings_hides_other_users(dummy_client, admin_user, dummy_user, jwt_dummy_user):
    # UserSettings.token is the password this user authenticates to Salt with.
    response = dummy_client.get("/api/userssettings/", **jwt_dummy_user)
    assert response.status_code == 200
    assert [row["user"] for row in response.json()] == [dummy_user.id]

    response = dummy_client.get(
        "/api/userssettings/{}/".format(admin_user.id), **jwt_dummy_user
    )
    assert response.status_code == 404


@pytest.mark.django_db()
def test_user_settings_rejects_writing_another_users_token(
    dummy_client, admin_user, dummy_user, jwt_dummy_user
):
    response = dummy_client.patch(
        "/api/userssettings/{}/".format(admin_user.id),
        {"token": "attacker-chosen"},
        content_type="application/json",
        **jwt_dummy_user
    )
    assert response.status_code == 404
    admin_user.user_settings.refresh_from_db()
    assert admin_user.user_settings.token != "attacker-chosen"


@pytest.mark.django_db()
def test_user_settings_token_is_read_only(dummy_client, dummy_user, jwt_dummy_user):
    original = dummy_user.user_settings.token
    response = dummy_client.patch(
        "/api/userssettings/{}/".format(dummy_user.id),
        {"token": "self-chosen", "settings": {"Layout": {"dark": True}}},
        content_type="application/json",
        **jwt_dummy_user
    )
    assert response.status_code == 200
    dummy_user.user_settings.refresh_from_db()
    # Preferences save; the Salt credential does not.
    assert dummy_user.user_settings.token == original
    assert dummy_user.user_settings.settings["Layout"]["dark"] is True


@pytest.mark.django_db()
def test_non_staff_cannot_change_alcali_records(
    dummy_client, dummy_user, jwt_dummy_user, minion
):
    # Reading stays open to any signed-in user.
    assert dummy_client.get("/api/minions/", **jwt_dummy_user).status_code == 200
    # Writing does not.
    assert (
        dummy_client.delete(
            "/api/minions/{}/".format(minion.minion_id), **jwt_dummy_user
        ).status_code
        == 403
    )
    assert (
        dummy_client.post(
            "/api/conformity/",
            {"name": "x", "function": "cmd.run"},
            content_type="application/json",
            **jwt_dummy_user
        ).status_code
        == 403
    )


@pytest.mark.django_db()
def test_staff_can_still_change_alcali_records(admin_client, jwt):
    response = admin_client.post(
        "/api/conformity/",
        {"name": "staffrule", "function": "cmd.run"},
        content_type="application/json",
        **jwt
    )
    assert response.status_code == 201


# --- request bodies ------------------------------------------------------


@pytest.mark.django_db()
def test_run_rejects_an_empty_body(admin_client, jwt):
    # The frontend sends JSON; these views read request.POST, which is empty for
    # a JSON body, and the view then returned None -> AssertionError -> 500.
    response = admin_client.post(
        "/api/run/", {}, content_type="application/json", **jwt
    )
    assert response.status_code == 400


@pytest.mark.django_db()
def test_refresh_minions_reads_a_json_minion_id(admin_client, jwt, monkeypatch):
    seen = {}

    def fake_refresh(minion_id):
        seen["minion_id"] = minion_id
        return {"result": "refreshed"}

    monkeypatch.setattr("api.views.alcali.refresh_minion", fake_refresh)
    response = admin_client.post(
        "/api/minions/refresh_minions/",
        {"minion_id": "minion1"},
        content_type="application/json",
        **jwt
    )
    assert response.status_code == 200
    # Without this the view fell through to the refresh-everything branch.
    assert seen == {"minion_id": "minion1"}


# --- fleet health --------------------------------------------------------


@pytest.mark.django_db()
def test_silent_reports_accepted_minions_that_stopped_returning(
    admin_client, jwt, key, minion
):
    import datetime

    from django.utils import timezone

    # `key` is an accepted key for 2e220fd40bc5 with no returns at all.
    body = admin_client.get("/api/minions/silent/?days=1", **jwt).json()
    assert body["accepted"] == 1
    assert [row["minion_id"] for row in body["silent"]] == ["2e220fd40bc5"]
    assert body["silent"][0]["reason"] == "never returned"

    # A recent return clears it.
    SaltReturns.objects.create(
        fun="test.ping", jid="20200101000000000001", return_field="{}",
        id="2e220fd40bc5", success="1", full_ret='{"success": true, "fun_args": []}',
        alter_time=timezone.now(),
    )
    body = admin_client.get("/api/minions/silent/?days=1", **jwt).json()
    assert body["silent"] == []

    # An old one does not.
    SaltReturns.objects.all().update(
        alter_time=timezone.now() - datetime.timedelta(days=5)
    )
    body = admin_client.get("/api/minions/silent/?days=1", **jwt).json()
    assert [row["reason"] for row in body["silent"]] == ["stale"]
    assert body["silent"][0]["days"] == 5


@pytest.mark.django_db()
def test_silent_ignores_keys_that_are_not_accepted(admin_client, jwt):
    Keys.objects.create(minion_id="rejected1", status="rejected", pub="x")
    body = admin_client.get("/api/minions/silent/", **jwt).json()
    assert body["accepted"] == 0
    assert body["silent"] == []


# --- targeting and search ------------------------------------------------


@pytest.mark.django_db()
def test_preview_target_evaluates_what_it_can(admin_client, jwt):
    import json as _json

    Minions.objects.create(
        minion_id="web01", grain=_json.dumps({"os": "Ubuntu", "role": "web"}),
        pillar=_json.dumps({"env": "prod"}),
    )
    Minions.objects.create(
        minion_id="db01", grain=_json.dumps({"os": "Debian", "role": "db"}),
        pillar=_json.dumps({"env": "staging"}),
    )

    def preview(tgt, tgt_type="glob"):
        return admin_client.get(
            "/api/minions/preview_target/?tgt={}&tgt_type={}".format(tgt, tgt_type),
            **jwt
        ).json()

    assert preview("web*")["matched"] == ["web01"]
    assert preview("*")["count"] == 2
    assert preview("web01,db01", "list")["matched"] == ["db01", "web01"]
    assert preview("os:Ubuntu", "grain")["matched"] == ["web01"]
    assert preview("env:prod", "pillar")["matched"] == ["web01"]


@pytest.mark.django_db()
def test_preview_target_refuses_what_it_cannot_evaluate(admin_client, jwt):
    # A wrong blast radius is worse than none, so compound expressions - which
    # only the master can resolve - are reported as not evaluated.
    body = admin_client.get(
        "/api/minions/preview_target/?tgt=G@os:Ubuntu and web*&tgt_type=compound",
        **jwt
    ).json()
    assert body["evaluated"] is False
    assert body["matched"] == []
    assert "compound" in body["reason"]


@pytest.mark.django_db()
def test_search_finds_a_minion_by_its_grains(admin_client, jwt):
    import json as _json

    Minions.objects.create(
        minion_id="web01",
        grain=_json.dumps({"os": "Ubuntu", "ipv4": ["10.0.3.14"]}),
        pillar=_json.dumps({}),
    )
    body = admin_client.get("/api/search/?q=10.0.3.14", **jwt).json()
    assert [m["minion_id"] for m in body["minions"]] == ["web01"]


# --- audit log -----------------------------------------------------------


@pytest.mark.django_db()
def test_alcali_changes_are_recorded(admin_client, admin_user, jwt, minion):
    from api.models import AuditLog

    admin_client.post(
        "/api/conformity/", {"name": "audited", "function": "cmd.run"},
        content_type="application/json", **jwt
    )
    admin_client.delete("/api/minions/{}/".format(minion.minion_id), **jwt)

    entries = {(e.action, e.target): e for e in AuditLog.objects.all()}
    assert ("conformity.create", "Conformity object (1)") in entries or any(
        a == "conformity.create" for a, _ in entries
    )
    assert ("minions.delete", minion.minion_id) in entries
    # The acting user is named, and kept as text so the record survives them.
    assert entries[("minions.delete", minion.minion_id)].username == admin_user.username


@pytest.mark.django_db()
def test_token_and_key_actions_are_recorded(admin_client, admin_user, jwt):
    from api.models import AuditLog

    admin_client.post(
        "/api/users/{}/manage_token/".format(admin_user.id),
        {"action": "renew"}, content_type="application/json", **jwt
    )
    assert AuditLog.objects.filter(
        action="token.renew", target=admin_user.username
    ).exists()


@pytest.mark.django_db()
def test_audit_log_is_staff_only(dummy_client, admin_client, jwt, jwt_dummy_user):
    assert dummy_client.get("/api/audit/", **jwt_dummy_user).status_code == 403
    assert admin_client.get("/api/audit/", **jwt).status_code == 200


@pytest.mark.django_db()
def test_a_failing_audit_write_does_not_break_the_action(
    admin_client, jwt, minion, monkeypatch
):
    # Auditing must never be the reason a user's change fails.
    def boom(*args, **kwargs):
        raise RuntimeError("audit backend down")

    monkeypatch.setattr("api.models.AuditLog.objects.create", boom)
    response = admin_client.delete("/api/minions/{}/".format(minion.minion_id), **jwt)
    assert response.status_code == 204
