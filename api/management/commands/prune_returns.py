"""Trim the Salt returner tables.

Salt's mysql returner never removes anything. `keep_jobs_seconds` governs the
master's own job cache, not this database, so `salt_returns`, `salt_events` and
`jids` grow for the life of the installation until something else prunes them.
Alcali already owns this connection, so it is a reasonable place to do it.
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import Jids, SaltEvents, SaltReturns

BATCH = 5000


class Command(BaseCommand):
    help = "Delete Salt returner rows older than a retention window"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            required=True,
            help="Delete rows whose alter_time is older than this many days.",
        )
        parser.add_argument(
            "--events-days",
            type=int,
            help="Separate window for salt_events, which grows fastest. "
            "Defaults to --days.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted and change nothing.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required to actually delete. Without it this is a dry run.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        events_days = options["events_days"] or days
        if events_days < 1:
            raise CommandError("--events-days must be at least 1")

        now = timezone.now()
        returns_before = now - datetime.timedelta(days=days)
        events_before = now - datetime.timedelta(days=events_days)
        commit = options["yes"] and not options["dry_run"]

        returns = SaltReturns.objects.filter(alter_time__lt=returns_before)
        events = SaltEvents.objects.filter(alter_time__lt=events_before)
        # A jids row is only useful while a return still refers to it.
        kept_jids = SaltReturns.objects.exclude(
            alter_time__lt=returns_before
        ).values("jid")
        stale_jids = Jids.objects.exclude(jid__in=kept_jids)

        counts = {
            "salt_returns": returns.count(),
            "salt_events": events.count(),
            "jids": stale_jids.count(),
        }
        for table, count in counts.items():
            self.stdout.write("{}: {} row(s) older than the window".format(table, count))

        if not commit:
            self.stdout.write("dry run; nothing deleted. Re-run with --yes to apply.")
            return

        deleted = {
            # salt_returns has no unique key - Django maps `id` (the minion) as
            # the primary key - so this must delete on the time predicate and
            # never by pk, which would take every row for those minions.
            "salt_returns": _delete_by_time(SaltReturns, returns_before),
            "salt_events": _delete_by_pk(SaltEvents, events),
            "jids": _delete_by_pk(Jids, stale_jids),
        }
        for table, count in deleted.items():
            self.stdout.write("{}: deleted {} row(s)".format(table, count))
        self.stdout.write(
            "Deleting rows does not shrink the files; run OPTIMIZE TABLE "
            "(or a rebuild) if you need the space back."
        )


def _delete_by_time(model, before, slice_days=1):
    """Delete oldest-first in time slices.

    One statement covering years of history would hold a very large
    transaction open; a day at a time keeps each one short.
    """
    total = 0
    oldest = model.objects.order_by("alter_time").values_list(
        "alter_time", flat=True
    ).first()
    if oldest is None:
        return 0
    cutoff = oldest
    while cutoff < before:
        cutoff = min(cutoff + datetime.timedelta(days=slice_days), before)
        with transaction.atomic():
            count, _ = model.objects.filter(alter_time__lt=cutoff).delete()
        total += count
    return total


def _delete_by_pk(model, queryset, batch=BATCH):
    """Delete in pk batches. Only safe where the pk is genuinely unique."""
    total = 0
    while True:
        with transaction.atomic():
            keys = list(queryset.values_list("pk", flat=True)[:batch])
            if not keys:
                return total
            count, _ = model.objects.filter(pk__in=keys).delete()
        if not count:
            return total
        total += count
