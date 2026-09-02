import os
from pathlib import Path

import pytest
from django.conf import settings
from django.db import connection

from api.models import Jids, SaltEvents, SaltReturns

from .fixtures import *


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Add Salt's externally managed tables to pytest-django's test database.

    `Jids`, `SaltReturns` and `SaltEvents` belong to the Salt returner schema,
    so they are ``managed = False`` and no migration creates them.

    Building the database by hand here instead of wrapping pytest-django's own
    fixture does not work: replacing ``settings.DATABASES`` after Django has
    instantiated its connection leaves the connection bound to the original
    settings, so the suite silently migrates the development database in the
    repository root and only passes on a checkout where that file is absent.

    Building them from the models is not good enough: Django maps
    ``salt_returns.id`` (the minion) as the primary key, so schema_editor's DDL
    makes it UNIQUE and the table cannot hold two returns for one minion. Salt's
    real schema has no primary key there, and code that assumes otherwise - a
    delete keyed on pk, say - would pass against a table that cannot reproduce
    the case. So the returner tables are created with Salt's own DDL.
    """
    settings.USE_TZ = False
    settings.SECRET_KEY = "alcali-tests-only-secret-key-at-least-32-bytes"
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE jids ("
                " jid varchar(255) NOT NULL PRIMARY KEY,"
                " load text NOT NULL)"
            )
            cursor.execute(
                "CREATE TABLE salt_returns ("
                " fun varchar(50) NOT NULL,"
                " jid varchar(255) NOT NULL,"
                ' "return" text NOT NULL,'
                " id varchar(255) NOT NULL,"
                " success varchar(10) NOT NULL,"
                " full_ret text NOT NULL,"
                " alter_time datetime NOT NULL)"
            )
            cursor.execute(
                "CREATE TABLE salt_events ("
                " id integer NOT NULL PRIMARY KEY AUTOINCREMENT,"
                " tag varchar(255) NOT NULL,"
                " data text NOT NULL,"
                " alter_time datetime NOT NULL,"
                " master_id varchar(255) NOT NULL)"
            )
    yield


@pytest.fixture(scope="session", autouse=True)
def frontend_shell():
    """Guarantee dist/index.html exists for the views that render it.

    dist/ is build output and no longer tracked, so a fresh checkout has none
    until `pnpm build` runs. The index and SPA-fallback tests assert on URL
    routing rather than bundle contents, so a placeholder is enough for them;
    a real build is left alone.
    """
    index = Path(settings.BASE_DIR) / "dist" / "index.html"
    if index.exists():
        yield
        return
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("<!doctype html><title>alcali</title><div id=app></div>")
    try:
        yield
    finally:
        index.unlink()
