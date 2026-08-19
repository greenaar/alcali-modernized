import os

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
    """
    settings.USE_TZ = False
    settings.SECRET_KEY = "alcali-tests-only-secret-key-at-least-32-bytes"
    with django_db_blocker.unblock():
        with connection.schema_editor() as schema_editor:
            for model in (Jids, SaltReturns, SaltEvents):
                schema_editor.create_model(model)
    yield
