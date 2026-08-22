import os

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import Error as DatabaseError

# Salt's returner tables. Alcali maps them as unmanaged models, so migrate
# never creates them; a deployment whose master is not returning to this
# database has none of them, and every job and event view is silently empty.
SALT_TABLES = ("jids", "salt_returns", "salt_events")


class Command(BaseCommand):
    help = "Check Alcali's database connection and required environment variables"

    def handle(self, *args, **options):
        required = [
            "MASTER_MINION_ID",
            "DB_BACKEND",
            "DB_NAME",
            "SECRET_KEY",
            "ALLOWED_HOSTS",
            "SALT_URL",
            "SALT_AUTH",
        ]
        if os.environ.get("DB_BACKEND", "sqlite3") != "sqlite3":
            required.extend(["DB_USER", "DB_PASS", "DB_HOST", "DB_PORT"])
        unset = [name for name in required if not os.environ.get(name)]

        connection = connections["default"]
        missing_tables = []
        try:
            connection.cursor()
        except DatabaseError as exc:
            database_error = exc
        else:
            database_error = None
            present = set(connection.introspection.table_names())
            missing_tables = [t for t in SALT_TABLES if t not in present]

        self.stdout.write(
            "db:\t{}\nenv:\t{}".format(database_error or "ok", unset or "ok")
        )
        # Reported, but not a failure: a development database has no returner
        # tables and does not need any.
        if missing_tables:
            self.stdout.write(
                "warning: Salt returner tables missing: {}. These are created by "
                "the Salt master's returner, not by migrate; job and event views "
                "stay empty without them.".format(", ".join(missing_tables))
            )

        # Exit non-zero when something is actually wrong, so this can gate a
        # deployment. A check command that always succeeds cannot be scripted
        # against.
        if database_error or unset:
            raise SystemExit(1)
