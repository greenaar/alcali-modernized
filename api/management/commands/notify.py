"""Evaluate the notification rules and send what changed.

Meant for cron or a Salt schedule. It is deliberately a command rather than
anything in the request path: evaluating every rule walks the whole fleet,
which has no business happening while somebody loads a page.
"""
import json

from django.core.management.base import BaseCommand

from api.notifications import run_rules


class Command(BaseCommand):
    help = "Send notifications for minions that have changed state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent, send nothing, and remember nothing.",
        )
        parser.add_argument(
            "--json", action="store_true", help="Emit the events as JSON."
        )

    def handle(self, *args, **options):
        events = run_rules(dry_run=options["dry_run"])
        if options["json"]:
            self.stdout.write(json.dumps(events, indent=2, default=str))
            return
        if not events:
            self.stdout.write("nothing changed")
            return
        for event in events:
            if event.get("error"):
                self.stderr.write(
                    "rule {}: {}".format(event["rule"], event["error"])
                )
                continue
            line = "{} {} ({}): {}".format(
                event["state"], event["minion"], event["rule"], event["reason"]
            )
            if event.get("errors"):
                line += "  [delivery failed: {}]".format("; ".join(event["errors"]))
            self.stdout.write(line)
