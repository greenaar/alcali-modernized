"""Drop every cached highstate verdict so it is recomputed under the new rule.

The cache is keyed on the newest state run, so a verdict only recomputes when
a run lands. Test runs no longer count as highstates, and a verdict cached
from one would otherwise survive until that minion's next state run - which
on a quiet minion could be a long time to keep reporting drift that is not
there. The table is Alcali's own and losing it costs a recomputation only.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    apps.get_model("api", "ConformityCache").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0010_returner_indexes"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
