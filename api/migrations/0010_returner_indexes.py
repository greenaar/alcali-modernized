"""Add the indexes Alcali's queries need to Salt's returner tables.

Those tables are unmanaged, so this is not a schema operation Django tracks:
it adds only what is missing, matched on leading columns so an equivalent
index an operator already made is left alone. Tables that do not exist yet
are skipped; `alcali returner_indexes --apply` covers them later.

Non-atomic because PostgreSQL's CREATE INDEX CONCURRENTLY cannot run inside a
transaction, and MySQL commits DDL implicitly anyway.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    from api.returner_indexes import ensure_indexes

    ensure_indexes(schema_editor.connection)


def backwards(apps, schema_editor):
    from api.returner_indexes import drop_indexes

    drop_indexes(schema_editor.connection)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("api", "0009_minion_id_indexes"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, elidable=False),
    ]
