"""The indexes Alcali adds to Salt's returner tables, and when it does not."""
import datetime
import json
import subprocess
import sys

import pytest
from django.core.management import call_command
from django.db import connection

from api import returner_indexes
from api.models import Jids, SaltReturns


def _index_names(table):
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table))


@pytest.fixture
def no_alcali_indexes(django_db_blocker):
    """Start from Salt's bare DDL, and leave it that way for the next test.

    DDL on SQLite does not roll back with pytest-django's transaction for
    every statement, so the indexes are dropped explicitly both sides.
    """
    returner_indexes.drop_indexes(connection, write=lambda *_: None)
    yield
    returner_indexes.drop_indexes(connection, write=lambda *_: None)
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS operator_own_alter_time")


@pytest.mark.django_db(transaction=True)
def test_all_are_reported_missing_on_salts_own_ddl(no_alcali_indexes):
    missing = {name for name, _t, _c in returner_indexes.missing_indexes(connection)}
    assert missing == {name for name, _t, _c in returner_indexes.RETURNER_INDEXES}


@pytest.mark.django_db(transaction=True)
def test_ensure_creates_them_once(no_alcali_indexes):
    created, failed = returner_indexes.ensure_indexes(connection, write=lambda *_: None)
    assert failed == []
    assert len(created) == len(returner_indexes.RETURNER_INDEXES)
    assert returner_indexes.missing_indexes(connection) == []
    assert "alcali_ret_id_fun_jid" in _index_names("salt_returns")
    # Idempotent: nothing left to do the second time.
    assert returner_indexes.ensure_indexes(connection, write=lambda *_: None) == ([], [])


@pytest.mark.django_db(transaction=True)
def test_an_equivalent_index_under_another_name_is_respected(no_alcali_indexes):
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE INDEX operator_own_alter_time ON salt_returns (alter_time, jid)"
        )
    returner_indexes.ensure_indexes(connection, write=lambda *_: None)
    names = _index_names("salt_returns")
    assert "operator_own_alter_time" in names
    assert "alcali_ret_alter_time" not in names


@pytest.mark.django_db(transaction=True)
def test_reverse_drops_only_its_own(no_alcali_indexes):
    with connection.cursor() as cursor:
        cursor.execute("CREATE INDEX operator_own_alter_time ON salt_events (alter_time)")
    returner_indexes.ensure_indexes(connection, write=lambda *_: None)
    returner_indexes.drop_indexes(connection, write=lambda *_: None)
    assert "operator_own_alter_time" in _index_names("salt_events")
    assert not {n for n, _t, _c in returner_indexes.RETURNER_INDEXES} & (
        _index_names("salt_returns") | _index_names("salt_events")
    )


@pytest.mark.django_db(transaction=True)
def test_a_failure_is_reported_not_raised(no_alcali_indexes, monkeypatch):
    # A database user without INDEX on Salt's tables must not block migrate.
    monkeypatch.setattr(
        returner_indexes, "create_sql", lambda *a: "CREATE INDEX broken ON nowhere (x)"
    )
    lines = []
    created, failed = returner_indexes.ensure_indexes(connection, write=lines.append)
    assert created == []
    assert len(failed) == len(returner_indexes.RETURNER_INDEXES)
    assert any("returner_indexes --apply" in line for line in lines)


@pytest.mark.django_db(transaction=True)
def test_the_command_checks_and_applies(no_alcali_indexes):
    with pytest.raises(SystemExit) as exit_:
        call_command("returner_indexes", "--check")
    assert exit_.value.code == 1
    call_command("returner_indexes", "--apply")
    call_command("returner_indexes", "--check")


@pytest.mark.django_db(transaction=True)
def test_the_migration_step_adds_them(no_alcali_indexes):
    import importlib

    migration = importlib.import_module("api.migrations.0010_returner_indexes")

    class Editor:
        pass

    editor = Editor()
    editor.connection = connection
    migration.forwards(None, editor)
    assert returner_indexes.missing_indexes(connection) == []


@pytest.mark.django_db()
def test_mysql_builds_online_or_not_at_all():
    class Ops:
        @staticmethod
        def quote_name(name):
            return "`{}`".format(name)

    class Conn:
        vendor = "mysql"
        ops = Ops()

    sql = returner_indexes.create_sql(Conn(), "i", "salt_returns", ("id", "fun"))
    assert sql.endswith("ALGORITHM=INPLACE, LOCK=NONE")
    Conn.vendor = "postgresql"
    assert "CONCURRENTLY" in returner_indexes.create_sql(Conn(), "i", "t", ("a",))


@pytest.mark.django_db()
def test_jobs_filters_survive_a_long_history(admin_client, jwt):
    # Every jid used to go back into one IN clause - past SQLite's variable
    # limit, and past max_allowed_packet on a real MySQL history.
    Jids.objects.bulk_create(
        Jids(jid="2026{:016d}".format(i), load=json.dumps({"user": "u{}".format(i % 3)}))
        for i in range(40000)
    )
    response = admin_client.get("/api/jobs/filters/", **jwt)
    assert response.status_code == 200
    assert set(response.json()["users"]) == {"u0", "u1", "u2"}


@pytest.mark.django_db()
def test_jobs_date_range_includes_the_whole_last_day(admin_client, jwt):
    for jid, when in (
        ("20260901000000000001", datetime.datetime(2026, 8, 31, 23, 59)),
        ("20260901000000000002", datetime.datetime(2026, 9, 1, 0, 0)),
        ("20260901000000000003", datetime.datetime(2026, 9, 2, 23, 59)),
        ("20260901000000000004", datetime.datetime(2026, 9, 3, 0, 0)),
    ):
        SaltReturns.objects.create(
            fun="test.ping", jid=jid, return_field="{}", id="m", success="1",
            full_ret="{}", alter_time=when,
        )
    body = admin_client.get("/api/jobs/?start=2026-09-01&end=2026-09-02", **jwt).json()
    assert sorted(r["jid"] for r in body) == [
        "20260901000000000002",
        "20260901000000000003",
    ]
    # A malformed date is ignored rather than a 500.
    response = admin_client.get("/api/jobs/?start=yesterday&end=today", **jwt)
    assert response.status_code == 200


def _child_env(**env):
    """This process's environment, minus anything that would steer logging.

    Inherited rather than built from scratch: a CI Python is often linked
    against a shared libpython found through LD_LIBRARY_PATH, and a child
    without it cannot even start.
    """
    import os

    full_env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("LOG_") and k not in ("DJANGO_SETTINGS_MODULE",)
    }
    full_env.update({"SECRET_KEY": "x", "DB_BACKEND": "sqlite3"})
    full_env.update(env)
    return full_env


def _logging_for(tmp_path, **env):
    """Import settings fresh in a child process and report its LOGGING."""
    script = (
        "import json, os; os.environ.setdefault('DB_BACKEND', 'sqlite3');"
        "import config.settings as s; print(json.dumps(s.LOGGING))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env=_child_env(**env), capture_output=True,
        text=True, check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1]), result.stderr


def test_logging_defaults_to_stderr_only(tmp_path):
    config, _ = _logging_for(tmp_path)
    assert set(config["handlers"]) == {"console"}
    assert config["root"]["level"] == "INFO"


def test_log_file_adds_a_watched_file_handler(tmp_path):
    path = tmp_path / "alcali.log"
    config, _ = _logging_for(tmp_path, LOG_FILE=str(path), LOG_LEVEL="warning")
    assert config["handlers"]["file"]["class"] == "logging.handlers.WatchedFileHandler"
    assert config["handlers"]["file"]["filename"] == str(path)
    assert set(config["root"]["handlers"]) == {"console", "file"}
    assert config["root"]["level"] == "WARNING"


def test_log_console_false_makes_the_file_the_only_destination(tmp_path):
    config, _ = _logging_for(tmp_path, LOG_FILE=str(tmp_path / "a.log"), LOG_CONSOLE="false")
    assert config["root"]["handlers"] == ["file"]


def test_an_unwritable_log_file_falls_back_rather_than_failing(tmp_path):
    config, stderr = _logging_for(
        tmp_path, LOG_FILE=str(tmp_path / "missing" / "a.log"), LOG_CONSOLE="false"
    )
    assert config["root"]["handlers"] == ["console"]
    assert "cannot write LOG_FILE" in stderr


def test_the_log_file_receives_application_logs(tmp_path):
    path = tmp_path / "alcali.log"
    script = (
        "import django, logging, warnings;"
        "django.setup();"
        "logging.getLogger('api.test').warning('hello from alcali');"
        "warnings.warn('a python warning')"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        env=_child_env(DJANGO_SETTINGS_MODULE="config.settings", LOG_FILE=str(path)),
        check=True, capture_output=True,
    )
    text = path.read_text()
    assert "WARNING" in text and "api.test: hello from alcali" in text
    assert "a python warning" in text
