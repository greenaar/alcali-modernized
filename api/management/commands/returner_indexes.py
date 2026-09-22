"""Report or add the indexes Alcali needs on Salt's returner tables.

Migration 0010 does this once. This is for everything after: returner tables
created after that migration ran, or a database user that lacked INDEX at the
time and has since been granted it.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from api.returner_indexes import ensure_indexes, missing_indexes


class Command(BaseCommand):
    help = "Report, or with --apply add, the returner-table indexes Alcali needs."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--apply", action="store_true", help="Create the missing indexes."
        )
        mode.add_argument(
            "--check",
            action="store_true",
            help="Print nothing; exit 1 if any are missing. For a state's `unless`.",
        )

    def handle(self, *args, **options):
        missing = missing_indexes(connection)
        if options["check"]:
            if missing:
                raise SystemExit(1)
            return
        if not missing:
            self.stdout.write("returner indexes: all present")
            return
        if not options["apply"]:
            for name, table, columns in missing:
                self.stdout.write(
                    "missing: {}({}) - would add as {}".format(
                        table, ", ".join(columns), name
                    )
                )
            self.stdout.write("run with --apply to add them")
            return
        _created, failed = ensure_indexes(connection, write=self.stdout.write)
        if failed:
            raise CommandError("{} index(es) could not be added".format(len(failed)))
        self.stdout.write("returner indexes: all present")
