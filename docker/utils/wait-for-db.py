#!/usr/bin/env python
"""Block until Django can open a connection to the configured database.

The demo stack used a TCP probe (`wait-for`), which reports success as soon
as something is listening. A database that is listening is not necessarily a
database that will accept an authenticated connection: MariaDB's entrypoint
binds the port while it is still initialising, and an external server may be
up but not yet have granted Alcali access. Migrating at that point fails, so
this probe uses the real connection instead.
"""
import os
import sys
import time

import django
from django.db import connections
from django.db.utils import Error as DjangoDatabaseError

TIMEOUT = float(os.environ.get("DB_WAIT_TIMEOUT", "120"))
INTERVAL = float(os.environ.get("DB_WAIT_INTERVAL", "2"))


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    deadline = time.monotonic() + TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        connection = connections["default"]
        try:
            connection.ensure_connection()
        except DjangoDatabaseError as exc:
            last_error = exc
            connection.close()
            time.sleep(INTERVAL)
            continue
        return 0

    print(f"Database not reachable after {TIMEOUT:g}s: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
