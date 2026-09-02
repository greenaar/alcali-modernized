import os

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import Error as DatabaseError

# Salt's returner tables. Alcali maps them as unmanaged models, so migrate
# never creates them; a deployment whose master is not returning to this
# database has none of them, and every job and event view is silently empty.
SALT_TABLES = ("jids", "salt_returns", "salt_events")

# Alcali orders by alter_time on nearly every query, but Salt's own DDL indexes
# salt_returns only by id, jid and fun, and salt_events only by tag. Without
# these the server scans and filesorts the whole table each time. See
# docs/returner-indexes.sql.
WANTED_INDEX_COLUMNS = {
    "salt_returns": (("alter_time",), ("id", "alter_time")),
    "salt_events": (("alter_time",),),
}


class Command(BaseCommand):
    help = "Check Alcali's database connection and required environment variables"

    def missing_indexes(self, connection, present_tables):
        """Which of the wanted indexes the returner tables do not have.

        Matched on leading columns rather than by name, because an operator may
        well have created an equivalent index under a different name.
        """
        missing = []
        for table, wanted in WANTED_INDEX_COLUMNS.items():
            if table not in present_tables:
                continue
            try:
                with connection.cursor() as cursor:
                    constraints = connection.introspection.get_constraints(
                        cursor, table
                    )
            except (DatabaseError, NotImplementedError):
                continue
            indexed = [
                tuple(c["columns"])
                for c in constraints.values()
                if c.get("index") or c.get("unique") or c.get("primary_key")
            ]
            for columns in wanted:
                if not any(existing[: len(columns)] == columns for existing in indexed):
                    missing.append("{}({})".format(table, ", ".join(columns)))
        return missing

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
            missing_indexes = self.missing_indexes(connection, present)

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

        # Also reported rather than fatal: the application works without these,
        # it just makes the database do far more work than it needs to.
        if missing_indexes:
            self.stdout.write(
                "warning: returner tables are missing indexes Alcali sorts on: "
                "{}. Salt's schema does not create them. Apply "
                "docs/returner-indexes.sql.".format(", ".join(missing_indexes))
            )

        # Exit non-zero when something is actually wrong, so this can gate a
        # deployment. A check command that always succeeds cannot be scripted
        # against.
        if database_error or unset:
            raise SystemExit(1)
