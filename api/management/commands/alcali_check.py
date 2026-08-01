import os

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


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

        try:
            connections["default"].cursor()
        except OperationalError as exc:
            database_error = exc
        else:
            database_error = None

        self.stdout.write(
            "db:\t{}\nenv:\t{}".format(database_error or "ok", unset or "ok")
        )
