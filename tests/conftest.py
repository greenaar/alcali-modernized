import os

from django.conf import settings
from django.db import connection
from django.core.management import call_command

from api.models import Jids, SaltEvents, SaltReturns

from .fixtures import *


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker, tmp_path_factory):
    """Use SQLite for fast tests and create Salt's externally managed tables."""
    database_path = tmp_path_factory.mktemp("alcali") / "test.sqlite3"
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(database_path),
        "ATOMIC_REQUESTS": True,
    }
    settings.USE_TZ = False
    settings.SECRET_KEY = "alcali-tests-only-secret-key-at-least-32-bytes"
    with django_db_blocker.unblock():
        call_command("migrate", verbosity=0, interactive=False)
        with connection.schema_editor() as schema_editor:
            for model in (Jids, SaltReturns, SaltEvents):
                schema_editor.create_model(model)
    yield
    connection.close()
