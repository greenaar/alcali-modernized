import os
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command, CommandError
from django.conf import settings


@pytest.mark.django_db
def test_check(monkeypatch):
    for name, value in {
        "MASTER_MINION_ID": "master",
        "DB_BACKEND": "sqlite3",
        "DB_NAME": ":memory:",
        "SECRET_KEY": "test-secret",
        "ALLOWED_HOSTS": "localhost",
        "SALT_URL": "https://salt.example.test:8080",
        "SALT_AUTH": "rest",
    }.items():
        monkeypatch.setenv(name, value)
    out = StringIO()
    call_command("diagnose", stdout=out)
    assert "db:\tok" in out.getvalue()
    assert "env:\tok" in out.getvalue()


@pytest.mark.django_db
def test_check_env_fail(monkeypatch):
    out = StringIO()
    salt_url = os.environ.get("SALT_URL")
    monkeypatch.delenv("SALT_URL", raising=False)
    # A missing required variable has to be a non-zero exit, otherwise the
    # command cannot gate a deployment.
    with pytest.raises(SystemExit) as exit_info:
        call_command("diagnose", stdout=out)
    assert exit_info.value.code == 1
    assert "db:\tok" in out.getvalue()
    assert "SALT_URL" in out.getvalue()
    if salt_url is not None:
        monkeypatch.setenv("SALT_URL", salt_url)


@pytest.mark.django_db
def test_manage_token(admin_user):
    current_token = admin_user.user_settings.token
    out = StringIO()
    call_command("manage_token", "admin", stdout=out)
    assert current_token in out.getvalue()


@pytest.mark.django_db
def test_manage_token_raises():
    out = StringIO()
    with pytest.raises(CommandError) as err:
        call_command("manage_token", "foo", stdout=out)
    assert "user foo does" in str(err.value)


@pytest.mark.django_db
def test_manage_token_reset(admin_user):
    current_token = admin_user.user_settings.token
    out = StringIO()
    call_command("manage_token", "admin", "-r", stdout=out)
    assert current_token not in out.getvalue()


def test_current_version():
    out = StringIO()
    call_command("current_version", stdout=out)
    assert "alcali version {}".format(settings.VERSION) in out.getvalue()


def test_location():
    out = StringIO()
    call_command("location", stdout=out)
    assert os.path.abspath(os.getcwd()) in out.getvalue()


@pytest.fixture
def check_env(monkeypatch):
    for name, value in {
        "MASTER_MINION_ID": "master",
        "DB_BACKEND": "sqlite3",
        "DB_NAME": ":memory:",
        "SECRET_KEY": "test-secret",
        "ALLOWED_HOSTS": "localhost",
        "SALT_URL": "https://salt.example.test:8080",
        "SALT_AUTH": "rest",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.django_db()
def test_diagnose_names_the_empty_caches(check_env):
    # The tables that sit empty when the Salt API is misconfigured are caches
    # of the master's state, not of the returner database. The check says so
    # and says what fills each, because an empty Minions page otherwise looks
    # identical to a fleet with no minions.
    out = StringIO()
    call_command("diagnose", stdout=out)
    assert "salt_minions" in out.getvalue() and "0 row(s)" in out.getvalue()
    assert "refresh_minions" in out.getvalue()


@pytest.mark.django_db()
def test_diagnose_reports_why_the_salt_login_fails(admin_user, check_env):
    from api.backend.salt_api import SaltApiError

    with mock.patch(
        "api.backend.salt_api.SaltApiClient.login",
        side_effect=SaltApiError("Salt API request failed: connection refused"),
    ):
        out = StringIO()
        with pytest.raises(SystemExit):
            call_command("diagnose", "--salt-user", admin_user.username, stdout=out)
    assert "connection refused" in out.getvalue()


@pytest.mark.django_db()
def test_diagnose_reports_a_missing_token(admin_user, check_env):
    admin_user.user_settings.token = "REVOKED"
    admin_user.user_settings.save()
    out = StringIO()
    with pytest.raises(SystemExit):
        call_command("diagnose", "--salt-user", admin_user.username, stdout=out)
    assert "revoked" in out.getvalue()


@pytest.mark.django_db()
def test_diagnose_spots_a_job_cache_that_is_not_written(check_env):
    """salt_returns filling while jids stays empty is the signature of a
    master_job_cache that is not writing - the master then cannot read its own
    jobs back, logs 'jid does not exist', and every Salt-backed action returns
    an empty result without an error."""
    from api.models import SaltReturns

    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000000", return_field="{}",
        id="minion1", success="1", full_ret='{"success": true, "fun_args": []}',
        alter_time="2026-09-02 01:00:00",
    )
    out = StringIO()
    call_command("diagnose", stdout=out)
    text = out.getvalue()
    assert "jids 0 row(s), salt_returns 1 row(s)" in text
    assert "master_job_cache is not writing" in text or "not in jids" in text


@pytest.mark.django_db()
def test_diagnose_is_quiet_when_the_job_cache_is_written(check_env):
    from api.models import Jids, SaltReturns

    Jids.objects.create(jid="20260902010000000000", load='{"user": "admin"}')
    SaltReturns.objects.create(
        fun="test.ping", jid="20260902010000000000", return_field="{}",
        id="minion1", success="1", full_ret='{"success": true, "fun_args": []}',
        alter_time="2026-09-02 01:00:00",
    )
    out = StringIO()
    call_command("diagnose", stdout=out)
    assert "not in jids" not in out.getvalue()


@pytest.mark.django_db()
def test_diagnose_reports_both_high_water_marks(check_env):
    """"Is the newest return's jid present" cannot tell a job cache that is
    keeping up from one that stopped recording an hour ago."""
    from api.models import Jids, SaltReturns

    Jids.objects.create(jid="20260902010000000000", load='{"user": "admin"}')
    for jid, when in (
        ("20260902010000000000", "2026-09-02 01:00:00"),
        ("20260902020000000000", "2026-09-02 02:00:00"),
    ):
        SaltReturns.objects.create(
            fun="test.ping", jid=jid, return_field="{}", id="minion1", success="1",
            full_ret='{"success": true, "fun_args": []}', alter_time=when,
        )
    out = StringIO()
    call_command("diagnose", stdout=out)
    text = out.getvalue()
    assert "newest job in salt_returns 20260902020000000000" in text
    assert "newest in jids 20260902010000000000" in text
    assert "job cache is behind the returns" in text
