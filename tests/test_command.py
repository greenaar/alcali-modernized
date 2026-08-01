import os
from io import StringIO

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
    call_command("alcali_check", stdout=out)
    assert "db:\tok" in out.getvalue()
    assert "env:\tok" in out.getvalue()


@pytest.mark.django_db
def test_check_env_fail(monkeypatch):
    out = StringIO()
    salt_url = os.environ.get("SALT_URL")
    monkeypatch.delenv("SALT_URL", raising=False)
    call_command("alcali_check", stdout=out)
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
