"""Fixture data for the frontend smoke run.

The frontend only fails in interesting ways when there is something to render:
an empty database hides broken columns, broken slots and broken charts alike.
"""
import datetime
import json

from django.contrib.auth.models import User
from django.db import connection

from api.models import (
    Conformity,
    Functions,
    JobTemplate,
    Jids,
    Keys,
    Minions,
    SaltEvents,
    SaltReturns,
    Schedule,
    UserSettings,
)

MINIONS = ["salt.example.test", "web01.example.test", "db01.example.test"]
GRAINS = {
    "salt.example.test": {"fqdn": "salt.example.test", "os": "Debian",
                          "oscodename": "bookworm", "kernelrelease": "6.1.0"},
    "web01.example.test": {"fqdn": "web01.example.test", "os": "Ubuntu",
                           "oscodename": "noble", "kernelrelease": "6.8.0"},
    "db01.example.test": {"fqdn": "db01.example.test", "os": "CentOS",
                          "oscodename": "stream9", "kernelrelease": "5.14.0"},
}


def create_returner_tables():
    """Create Salt's unmanaged tables with the master's own schema.

    `salt_returns` has no primary key on `id`, so the schema editor's model
    derived DDL (which makes `id` one) cannot hold more than one row per minion.
    """
    with connection.cursor() as c:
        c.execute("DROP TABLE IF EXISTS salt_returns")
        c.execute("DROP TABLE IF EXISTS salt_events")
        c.execute("DROP TABLE IF EXISTS jids")
        c.execute("CREATE TABLE jids (jid varchar(255) NOT NULL PRIMARY KEY, load text NOT NULL)")
        c.execute(
            "CREATE TABLE salt_returns (fun varchar(50) NOT NULL, jid varchar(255) NOT NULL,"
            " return text NOT NULL, id varchar(255) NOT NULL, success varchar(10) NOT NULL,"
            " full_ret text NOT NULL, alter_time datetime NOT NULL)"
        )
        c.execute(
            "CREATE TABLE salt_events (id integer NOT NULL PRIMARY KEY AUTOINCREMENT,"
            " tag varchar(255) NOT NULL, data text NOT NULL, alter_time datetime NOT NULL,"
            " master_id varchar(255) NOT NULL)"
        )


def seed(username="smoke-admin", password="smoke-password-123"):
    user, _ = User.objects.get_or_create(
        username=username, defaults={"email": "smoke@example.test"}
    )
    user.is_staff = user.is_superuser = True
    user.set_password(password)
    user.save()
    UserSettings.objects.get_or_create(user=user)

    Minions.objects.all().delete()
    for name in MINIONS:
        Minions.objects.create(
            minion_id=name,
            grain=json.dumps(GRAINS[name]),
            pillar=json.dumps({"role": "smoke"}),
        )

    Keys.objects.all().delete()
    # never-returned.example.test has an accepted key and no returns at all,
    # which is what the fleet-health card is for.
    for name, status in [
        ("never-returned.example.test", "accepted"),
        (MINIONS[0], "accepted"), (MINIONS[1], "accepted"), (MINIONS[2], "accepted"),
        ("old01.example.test", "rejected"), ("rogue.example.test", "denied"),
        ("new01.example.test", "unaccepted"),
    ]:
        Keys.objects.create(minion_id=name, status=status, pub="ab:cd:ef:" + name[:6])

    Schedule.objects.all().delete()
    for name in MINIONS:
        Schedule.objects.create(minion=name, name="highstate", job=json.dumps(
            {"function": "state.apply", "enabled": True, "seconds": 3600, "maxrunning": 1}))
        Schedule.objects.create(minion=name, name="cleanup", job=json.dumps(
            {"function": "cmd.run", "enabled": False, "cron": "0 3 * * *", "maxrunning": 1}))

    Conformity.objects.all().delete()
    Conformity.objects.create(name="uptime", function="status.uptime")

    Functions.objects.all().delete()
    for name in ["test.ping", "state.apply", "cmd.run", "grains.items"]:
        Functions.objects.create(name=name, type="local", description="doc for " + name)

    JobTemplate.objects.all().delete()
    JobTemplate.objects.create(name="ping all", job=json.dumps(
        {"client": "local", "tgt": "*", "fun": "test.ping", "arg": [],
         "tgt_type": "glob", "batch": None}))

    SaltReturns.objects.all().delete()
    Jids.objects.all().delete()
    SaltEvents.objects.all().delete()
    base = datetime.datetime(2026, 9, 1, 18, 0, 0)
    first = None
    for i in range(12):
        jid = "20260902010000%06d" % i
        minion = MINIONS[i % 3]
        highstate = i % 4 == 0
        fun = "state.apply" if highstate else "test.ping"
        ok = i % 5 != 0
        payload = (
            {"pkg_|-x_|-x_|-installed": {"result": ok, "comment": "ok", "changes": {}}}
            if highstate else "pong"
        )
        full = {"fun": fun, "jid": jid, "return": payload, "retcode": 0 if ok else 1,
                "success": ok, "fun_args": [], "id": minion}
        Jids.objects.create(jid=jid, load=json.dumps(
            {"user": "smoke-admin", "fun": fun, "tgt": minion, "arg": []}))
        # A published event naming a minion that never returns, so the job
        # reconciliation has something to report.
        SaltEvents.objects.create(
            tag="salt/job/%s/new" % jid,
            data=json.dumps({"jid": jid, "fun": fun, "tgt": minion,
                             "minions": [minion, "never-returned.example.test"]}),
            alter_time=base - datetime.timedelta(minutes=i * 13, seconds=2),
            master_id="master")
        SaltReturns.objects.create(
            fun=fun, jid=jid, return_field=json.dumps(payload), id=minion,
            success=str(ok), full_ret=json.dumps(full),
            alter_time=base - datetime.timedelta(minutes=i * 13))
        SaltEvents.objects.create(
            tag="salt/job/%s/ret/%s" % (jid, minion),
            data=json.dumps({"jid": jid, "fun": fun, "fun_args": [], "id": minion,
                             "success": ok, "return": payload}),
            alter_time=base - datetime.timedelta(minutes=i * 13), master_id="master")
        # A row the parser cannot read: one of these used to blank the table.
        SaltEvents.objects.create(
            tag="salt/auth", data="not valid json",
            alter_time=base - datetime.timedelta(minutes=i * 13, seconds=1),
            master_id="master")
        if first is None:
            first = (jid, minion)
    return {"username": username, "password": password, "job": first}
