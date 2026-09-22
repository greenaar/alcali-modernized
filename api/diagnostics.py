"""Structured answers to "why is this page empty?".

The failures that cost the most time here are not Alcali errors: the master
answers, the request succeeds, and a page is simply blank because a Salt
client is not enabled, an eauth block is missing, or the master cannot read
its own job cache back. None of those surface as an exception, so each one
had to be found by hand.

These are the same checks `manage.py diagnose` runs, returned as data so
they can be shown in the UI. Each is independent and reports its own status:
one failing check must not stop the others from running, because knowing
which ones still pass is what localises the fault.
"""
import logging
import os

from django.db import DatabaseError, connection

logger = logging.getLogger(__name__)

OK, WARN, FAIL, UNKNOWN = "ok", "warn", "fail", "unknown"


def _check(key, label, status, detail="", hint=""):
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
        "hint": hint,
    }


def _salt_client(user):
    """Log in exactly as a Salt-backed request does."""
    from api.backend.salt_api import SaltApiClient

    url = os.environ.get("SALT_URL", "https://127.0.0.1:8080")
    eauth = os.environ.get("SALT_AUTH", "rest")
    token = getattr(getattr(user, "user_settings", None), "token", "")
    api = SaltApiClient(url)
    api.login(getattr(user, "username", ""), token, eauth)
    return api, url, eauth


def salt_checks(user):
    """Reachability and each netapi client, in the order they stop working."""
    from api.backend.salt_api import SaltApiError

    url = os.environ.get("SALT_URL", "https://127.0.0.1:8080")
    eauth = os.environ.get("SALT_AUTH", "rest")
    token = getattr(getattr(user, "user_settings", None), "token", "")

    if not token:
        return [
            _check(
                "salt.login",
                "Salt API login",
                FAIL,
                "{} has no Salt token stored".format(getattr(user, "username", "?")),
                "Settings -> your user -> generate a token.",
            )
        ]
    if token == "REVOKED":
        return [
            _check("salt.login", "Salt API login", FAIL, "the token was revoked",
                   "Generate a new token in Settings.")
        ]

    try:
        api, url, eauth = _salt_client(user)
    except SaltApiError as exc:
        hint = ""
        if "401" in str(exc) or "Unauthorized" in str(exc):
            hint = (
                "The master needs keep_acl_in_token: true and an external_auth "
                "block for eauth '{}' whose ^url points back at this Alcali's "
                "/api/token/verify/. That host must also be in ALLOWED_HOSTS "
                "here, or Django answers the master with 400.".format(eauth)
            )
        return [
            _check("salt.login", "Salt API login", FAIL,
                   "{} ({})".format(exc, url), hint)
        ]
    except Exception as exc:  # noqa: BLE001 - diagnostics must not raise
        return [_check("salt.login", "Salt API login", FAIL, str(exc))]

    checks = [
        _check("salt.login", "Salt API login", OK,
               "signed in to {} with eauth {}".format(url, eauth))
    ]

    # Wheel: the Keys page. Runner: minion presence and the grain cache.
    # Local: everything that talks to a minion.
    for key, label, call, page, client in (
        ("salt.wheel", "Wheel client", lambda a: a.wheel("key.list_all"),
         "Keys", "wheel"),
        ("salt.runner", "Runner client", lambda a: a.runner("manage.status"),
         "minion presence", "runner"),
        ("salt.local", "Local client", lambda a: a.local("*", "test.ping"),
         "Minions and Run", "local"),
    ):
        try:
            result = call(api)
        except SaltApiError as exc:
            checks.append(_check(
                key, label, FAIL, str(exc),
                "The master's netapi_enable_clients must list `{}`, and this "
                "user's eauth ACL must allow it. Without it the {} page stays "
                "empty.".format(client, page),
            ))
            continue
        except Exception as exc:  # noqa: BLE001
            checks.append(_check(key, label, FAIL, str(exc)))
            continue
        checks.append(_check(key, label, OK, "answered"))

        # The one that cost the most time: the local client answering while
        # the master collects nothing. Every minion comes back False, which
        # reads as "they said no" and is nothing of the kind.
        if key == "salt.local":
            checks.append(_return_collection_check(result))

    return checks


def _return_collection_check(result):
    """Whether the master actually collected the returns it published for."""
    try:
        returns = (result or {}).get("return", [{}])[0]
    except (AttributeError, IndexError, TypeError):
        returns = {}
    if not isinstance(returns, dict) or not returns:
        return _check(
            "salt.collection", "Return collection", UNKNOWN,
            "test.ping matched no minions, so there was nothing to collect",
        )
    answered = [minion for minion, value in returns.items() if value is not False]
    if answered:
        return _check(
            "salt.collection", "Return collection", OK,
            "{} of {} minion(s) returned".format(len(answered), len(returns)),
        )
    return _check(
        "salt.collection", "Return collection", FAIL,
        "all {} targeted minion(s) came back False".format(len(returns)),
        "That is not the minions answering no - it is the master's placeholder "
        "for minions it published to but could not collect from. Check "
        "`salt-run jobs.lookup_jid <jid>` on the master: if that works while "
        "this does not, the fault is inside the salt-api process rather than "
        "the master, and restarting salt-api usually clears it.",
    )


def job_cache_checks():
    """Is the master writing `jids`, not just the returns?

    They are separate writes, and only `jids` is what the master reads back
    when collecting a job. When it is not being written the master logs
    "jid does not exist" and abandons the job with no error at all.
    """
    from api.models import Jids, SaltReturns

    try:
        jids = Jids.objects.count()
        returns = SaltReturns.objects.count()
    except DatabaseError as exc:
        return [_check("cache.job", "Job cache", UNKNOWN,
                       "the returner tables could not be read: {}".format(exc))]

    detail = "jids {} row(s), salt_returns {} row(s)".format(jids, returns)
    if not returns:
        return [_check("cache.job", "Job cache", UNKNOWN,
                       detail + " - nothing has been recorded yet")]

    newest_return = (
        SaltReturns.objects.order_by("-alter_time")
        .values_list("jid", flat=True)
        .first()
    )
    newest_jid = Jids.objects.order_by("-jid").values_list("jid", flat=True).first()
    detail += "; newest return {}, newest jid {}".format(
        newest_return or "none", newest_jid or "none"
    )

    if newest_return and not Jids.objects.filter(jid=newest_return).exists():
        return [_check(
            "cache.job", "Job cache", FAIL, detail,
            "The newest job has a row in salt_returns but none in jids: the "
            "returner is writing results while master_job_cache is not writing "
            "the job cache. The master cannot read its own jobs back, so it "
            "logs 'jid does not exist' and returns nothing.",
        )]
    if newest_return and newest_jid and newest_jid < newest_return:
        return [_check(
            "cache.job", "Job cache", WARN, detail,
            "The job cache is behind the returns: jobs are being recorded that "
            "the master did not write to jids.",
        )]
    return [_check("cache.job", "Job cache", OK, detail)]


def index_checks():
    """Indexes the returner tables want but may not have.

    Matched on leading columns rather than by name: an operator may well have
    made an equivalent index under another name.
    """
    from api.returner_indexes import missing_indexes

    try:
        missing = missing_indexes(connection)
    except (DatabaseError, NotImplementedError) as exc:
        return [_check("db.indexes", "Returner indexes", UNKNOWN, str(exc))]

    if not missing:
        return [_check("db.indexes", "Returner indexes", OK,
                       "the columns Alcali filters and sorts on are indexed")]
    return [_check(
        "db.indexes", "Returner indexes", WARN,
        "missing: {}".format(", ".join(
            "{}({})".format(table, ", ".join(columns)) for _n, table, columns in missing
        )),
        "Migrations add these, so they are missing either because the returner "
        "tables were created after `alcali migrate` ran or because the database "
        "user lacks INDEX on them. Run `alcali returner_indexes --apply`. "
        "Without them the jobs list, the minions list and the retention counts "
        "scan the whole table.",
    )]


def cache_checks():
    """Which of Alcali's own caches are empty, and what fills each."""
    from api.models import Beacon, Keys, Minions, Schedule

    checks = []
    for label, model, filled_by in (
        ("Minions", Minions, "Minions -> refresh"),
        ("Keys", Keys, "Keys -> refresh"),
        ("Schedules", Schedule, "Schedules -> refresh"),
        ("Beacons", Beacon, "Beacons -> refresh from minions"),
    ):
        try:
            count = model.objects.count()
        except DatabaseError as exc:
            checks.append(_check("cache." + label.lower(), label + " cache",
                                 UNKNOWN, str(exc)))
            continue
        if count:
            checks.append(_check("cache." + label.lower(), label + " cache", OK,
                                 "{} row(s)".format(count)))
        else:
            checks.append(_check(
                "cache." + label.lower(), label + " cache", WARN, "empty",
                "This page reads a cache rather than Salt directly. Fill it "
                "with {}.".format(filled_by),
            ))
    return checks


def collect(user=None):
    """Every check, each isolated so one failure cannot hide the rest."""
    checks = []
    for name, runner in (
        ("salt", lambda: salt_checks(user)),
        ("job cache", job_cache_checks),
        ("caches", cache_checks),
        ("indexes", index_checks),
    ):
        try:
            checks.extend(runner())
        except Exception as exc:  # noqa: BLE001 - a broken check is not an outage
            logger.exception("diagnostic group %s failed", name)
            checks.append(_check(name, name.title() + " checks", UNKNOWN,
                                 "the check itself failed: {}".format(exc)))
    return checks
