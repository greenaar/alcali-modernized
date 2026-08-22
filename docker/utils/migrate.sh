#!/usr/bin/env bash
# One-shot schema job for the production stack. Kept out of the web service's
# start-up path so that scaling gunicorn never runs concurrent migrations.
set -Eeuo pipefail

cd /opt/alcali/code

python docker/utils/wait-for-db.py
python manage.py migrate --noinput

# Alcali reads Salt's returner tables (jids, salt_returns, salt_events) as
# unmanaged models, so migrate never creates them. Say so plainly rather than
# letting the first page load fail with a missing-table error.
python - <<'PY'
import django, os, sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connections

expected = {"jids", "salt_returns", "salt_events"}
present = set(connections["default"].introspection.table_names())
missing = sorted(expected - present)
if missing:
    print(
        "warning: Salt returner tables missing: {}\n"
        "         Alcali reads these; they are created by the Salt master's\n"
        "         returner schema, not by migrate. See docs/docs/docker.md.".format(
            ", ".join(missing)
        ),
        file=sys.stderr,
    )
PY
