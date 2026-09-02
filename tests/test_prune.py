import datetime

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from api.models import Jids, SaltEvents, SaltReturns


@pytest.fixture
def history():
    """Two minions, each with an old and a recent return, plus their jids."""
    now = timezone.now()
    rows = []
    for minion in ("minion1", "minion2"):
        for age_days, tag in ((90, "old"), (1, "recent")):
            jid = "2026{}{}".format(minion[-1], age_days)
            Jids.objects.create(jid=jid, load='{"user": "admin"}')
            rows.append(
                SaltReturns.objects.create(
                    fun="test.ping", jid=jid, return_field="{}", id=minion,
                    success="1", full_ret='{"success": true, "fun_args": []}',
                    alter_time=now - datetime.timedelta(days=age_days),
                )
            )
            SaltEvents.objects.create(
                tag="salt/job/{}/ret/{}".format(jid, minion), data="{}",
                alter_time=now - datetime.timedelta(days=age_days),
                master_id="master",
            )
    return rows


@pytest.mark.django_db()
def test_dry_run_by_default(history, capsys):
    call_command("prune_returns", "--days", "30")
    assert SaltReturns.objects.count() == 4
    assert "dry run" in capsys.readouterr().out


@pytest.mark.django_db()
def test_prune_keeps_rows_inside_the_window(history):
    call_command("prune_returns", "--days", "30", "--yes")
    # The crucial property: salt_returns has no unique key, so a pk-based
    # delete would have taken every row belonging to those minions.
    remaining = SaltReturns.objects.all()
    assert remaining.count() == 2
    assert {r.id for r in remaining} == {"minion1", "minion2"}
    assert all(r.alter_time > timezone.now() - datetime.timedelta(days=30)
               for r in remaining)


@pytest.mark.django_db()
def test_prune_drops_orphaned_jids_only(history):
    call_command("prune_returns", "--days", "30", "--yes")
    kept = set(Jids.objects.values_list("jid", flat=True))
    assert kept == set(SaltReturns.objects.values_list("jid", flat=True))
    assert len(kept) == 2


@pytest.mark.django_db()
def test_events_take_their_own_window(history):
    call_command("prune_returns", "--days", "365", "--events-days", "30", "--yes")
    # Returns are inside the 365-day window, events are not.
    assert SaltReturns.objects.count() == 4
    assert SaltEvents.objects.count() == 2


@pytest.mark.django_db()
def test_rejects_a_nonsense_window(history):
    with pytest.raises(CommandError):
        call_command("prune_returns", "--days", "0", "--yes")
    assert SaltReturns.objects.count() == 4
