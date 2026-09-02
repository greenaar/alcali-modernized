"""Pushing the two signals the dashboard already computes.

Conformity and silence are both visible in the UI, which only helps someone
who happens to be looking. These are the same signals delivered outward.

Alerts fire on a transition, never on a state: a rule that repeated itself
every run would be ignored within a week, which is worse than no alerting at
all. Recoveries are sent for the same reason - an alert with no closing
message leaves people guessing.
"""
import datetime
import logging

from django.conf import settings
from django.db.models import Max
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def _conformity_offenders():
    """Minions whose most recent highstate did not pass."""
    from api.models import Minions

    offenders = {}
    for minion in Minions.objects.all():
        if minion.conformity() is False:
            offenders[minion.minion_id] = "last highstate did not pass"
    return offenders


def _silent_offenders(days):
    """Accepted minions with nothing in the returner lately.

    A minion that stops answering leaves no row behind, so it cannot be found
    by looking at returns alone - the accepted keys are the roster.
    """
    from api.models import Keys, SaltReturns

    cutoff = timezone.now() - datetime.timedelta(days=days)
    accepted = list(
        Keys.objects.filter(status="accepted").values_list("minion_id", flat=True)
    )
    if not accepted:
        return {}
    seen = dict(
        SaltReturns.objects.filter(id__in=accepted)
        .values_list("id")
        .annotate(last=Max("alter_time"))
    )
    offenders = {}
    for minion_id in accepted:
        last = seen.get(minion_id)
        if last is None:
            offenders[minion_id] = "has never returned anything"
        elif last < cutoff:
            offenders[minion_id] = "last returned {}".format(
                last.strftime("%Y-%m-%d %H:%M")
            )
    return offenders


def offenders_for(rule):
    from api.models import NotificationRule

    if rule.trigger == NotificationRule.SILENT:
        return _silent_offenders(max(1, rule.threshold_days))
    return _conformity_offenders()


def transitions(rule):
    """What changed since this rule last looked.

    Returns (newly alerting, recovered), each a mapping of minion to reason.
    """
    from api.models import NotificationState

    current = offenders_for(rule)
    known = {s.minion_id: s for s in rule.states.all()}

    firing, recovered = {}, {}
    for minion_id, reason in current.items():
        state = known.get(minion_id)
        if state is None or state.state != NotificationState.ALERTING:
            firing[minion_id] = reason
    for minion_id, state in known.items():
        if state.state == NotificationState.ALERTING and minion_id not in current:
            recovered[minion_id] = "no longer matches this rule"
    return firing, recovered


def record(rule, minion_id, state):
    from api.models import NotificationState

    NotificationState.objects.update_or_create(
        rule=rule, minion_id=minion_id, defaults={"state": state}
    )


def _payload(rule, minion_id, reason, state):
    return {
        "rule": rule.name,
        "trigger": rule.trigger,
        "minion": minion_id,
        "state": state,
        "reason": reason,
        "at": timezone.now().isoformat(),
    }


def _send_webhook(rule, payload):
    import requests

    requests.post(rule.webhook_url, json=payload, timeout=10).raise_for_status()


def _send_email(rule, payload):
    subject = "[alcali] {} {}: {}".format(
        payload["minion"],
        "recovered" if payload["state"] == "clear" else "needs attention",
        rule.name,
    )
    body = "{}\n\nMinion: {}\nRule: {}\nTrigger: {}\nDetail: {}\nAt: {}\n".format(
        subject, payload["minion"], rule.name, rule.trigger,
        payload["reason"], payload["at"],
    )
    send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, rule.recipients(),
        fail_silently=False,
    )


def deliver(rule, payload):
    """Send one event down every channel the rule configures.

    One channel failing must not stop the other: the whole point is that
    somebody hears about this, and losing the email because a webhook
    endpoint is down would defeat it.
    """
    errors = []
    if rule.webhook_url:
        try:
            _send_webhook(rule, payload)
        except Exception as exc:  # noqa: BLE001 - report, do not raise
            logger.warning("webhook for rule %s failed: %s", rule.name, exc)
            errors.append("webhook: {}".format(exc))
    if rule.recipients():
        try:
            _send_email(rule, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("email for rule %s failed: %s", rule.name, exc)
            errors.append("email: {}".format(exc))
    return errors


def run_rules(dry_run=False):
    """Evaluate every enabled rule and dispatch what changed."""
    from api.models import NotificationRule, NotificationState

    events = []
    for rule in NotificationRule.objects.filter(enabled=True):
        try:
            firing, recovered = transitions(rule)
        except Exception as exc:  # noqa: BLE001 - one bad rule is not an outage
            logger.exception("rule %s could not be evaluated", rule.name)
            events.append({"rule": rule.name, "error": str(exc)})
            continue

        for minion_id, reason in sorted(firing.items()):
            payload = _payload(rule, minion_id, reason, NotificationState.ALERTING)
            errors = [] if dry_run else deliver(rule, payload)
            # Recorded even when delivery failed: retrying every run would
            # turn one unreachable webhook into a flood once it came back.
            if not dry_run:
                record(rule, minion_id, NotificationState.ALERTING)
            events.append(dict(payload, errors=errors))

        for minion_id, reason in sorted(recovered.items()):
            payload = _payload(rule, minion_id, reason, NotificationState.CLEAR)
            errors = [] if dry_run else deliver(rule, payload)
            if not dry_run:
                record(rule, minion_id, NotificationState.CLEAR)
            events.append(dict(payload, errors=errors))
    return events
