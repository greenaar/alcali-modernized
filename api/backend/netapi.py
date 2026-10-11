import hashlib
import os
import json
import threading
import time
from django_currentuser.middleware import get_current_user

from .salt_api import SaltApiClient, SaltApiError
from ..utils.input import RawCommand
from ..models import Minions, Functions, MinionsCustomFields, Keys, Schedule, Beacon

url = os.environ.get("SALT_URL", "https://127.0.0.1:8080")

# salt-api tokens held per process, so that a page does not pay for a login per
# call. Every view that touches Salt goes through api_connect(), and some of
# them loop: refreshing the Minions page asks each minion for its grains and
# its pillar in turn, which on a fleet of 45 was 46 logins for one page. With
# the `rest` eauth backend each of those makes the master call back to this
# process to verify the credential, so the cost is a round trip to Alcali, a
# master authentication and a database write, per call.
#
# Keyed on the credential as well as the user: regenerating someone's Salt
# token has to stop the token issued for the old one from being reused, and a
# key that ignored it would keep that session alive until `token_expire`.
#
# Per process rather than shared: with several gunicorn workers this is one
# login each per token lifetime, which is cheap, and it keeps a cache miss from
# depending on anything outside this process.
_TOKEN_CACHE: dict[tuple[str, str, str], dict] = {}
_TOKEN_LOCK = threading.Lock()

# Treat a token as spent slightly before the master does, so a call cannot be
# issued with one that expires in flight.
_TOKEN_EXPIRY_MARGIN = 30.0

# How long to trust a login response that does not say when it expires. The
# master always sends `expire`, so this is only reached against something that
# does not behave like salt-api.
_TOKEN_FALLBACK_TTL = 600.0


def _token_cache_enabled() -> bool:
    return os.environ.get("SALT_TOKEN_CACHE", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _cache_key(username: str, credential: str, eauth: str) -> tuple[str, str, str]:
    digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()[:16]
    return (username, eauth, digest)


def forget_salt_token(username: str, credential: str, eauth: str) -> None:
    """Drop a cached token, so the next call logs in again."""
    with _TOKEN_LOCK:
        _TOKEN_CACHE.pop(_cache_key(username, credential, eauth), None)


def _login(api, username: str, credential: str, eauth: str) -> dict:
    """Log in and cache the result. Returns the cache entry."""
    login_ret = api.login(username, credential, eauth)
    expire = login_ret.get("expire")
    try:
        expire = float(expire)
    except (TypeError, ValueError):
        expire = time.time() + _TOKEN_FALLBACK_TTL
    entry = {
        "token": login_ret["token"],
        "expire": expire,
        "perms": login_ret.get("perms"),
    }
    if _token_cache_enabled():
        now = time.time()
        with _TOKEN_LOCK:
            # Regenerating a token leaves its old entry unreachable, since the
            # key covers the credential. Clear anything spent while here, so
            # the cache cannot grow one dead entry per regeneration.
            for key in [
                key
                for key, held in _TOKEN_CACHE.items()
                if held["expire"] - _TOKEN_EXPIRY_MARGIN <= now
            ]:
                del _TOKEN_CACHE[key]
            _TOKEN_CACHE[_cache_key(username, credential, eauth)] = entry
    return entry


def _cached_entry(username: str, credential: str, eauth: str) -> dict | None:
    if not _token_cache_enabled():
        return None
    with _TOKEN_LOCK:
        entry = _TOKEN_CACHE.get(_cache_key(username, credential, eauth))
    if entry is None:
        return None
    if entry["expire"] - _TOKEN_EXPIRY_MARGIN <= time.time():
        forget_salt_token(username, credential, eauth)
        return None
    return entry


def first_return(api_ret, what="the Salt API"):
    """The first element of a Salt response's `return` list.

    salt-api answers with an empty list when a client collected nothing - which
    the local client does whenever the master cannot read the job back - so
    indexing straight into it raised IndexError and surfaced as a Django 500
    page rather than as the Salt failure it is.
    """
    if not isinstance(api_ret, dict):
        raise SaltApiError("{} returned {}, not a mapping".format(what, type(api_ret).__name__))
    returned = api_ret.get("return")
    if not isinstance(returned, list) or not returned:
        raise SaltApiError(
            "{} returned no result. The master accepted the call and collected "
            "nothing, which for a minion-targeted call usually means it could "
            "not read the job back from its job cache.".format(what)
        )
    return returned[0]


def api_connect():
    user = get_current_user()
    if user is None or not user.is_authenticated:
        raise SaltApiError("An authenticated Alcali user is required")
    username = str(user.username)
    credential = user.user_settings.token
    eauth = os.environ.get("SALT_AUTH", "rest")

    api = SaltApiClient(url)
    entry = _cached_entry(username, credential, eauth)
    if entry is None:
        entry = _login(api, username, credential, eauth)
    else:
        api.use_token(entry["token"])

    # The master can expire or forget a token before it says it will - most
    # obviously across a restart. The client calls this when salt-api refuses a
    # request, and retries it once with what comes back.
    def reauth():
        forget_salt_token(username, credential, eauth)
        return _login(api, username, credential, eauth)["token"]

    api.reauth = reauth

    # Written only when it changes. This used to be assigned on the settings
    # row and then saved through `user.save()`, which saves the user and not
    # the related row, so the value never actually reached the database.
    perms = json.dumps(entry["perms"])
    if user.user_settings.salt_permissions != perms:
        user.user_settings.salt_permissions = perms
        user.user_settings.save(update_fields=["salt_permissions"])
    return api


def get_keys(refresh=False):
    if refresh:
        # Salt return to minion status.
        minion_status = {
            "minions_rejected": "rejected",
            "minions_denied": "denied",
            "minions_pre": "unaccepted",
            "minions": "accepted",
        }

        try:
            api = api_connect()
            api_ret = api.wheel("key.list_all")["return"][0]["data"]["return"]
        except SaltApiError as e:
            return {"error": str(e)}

        Keys.objects.all().delete()
        for key, value in minion_status.items():
            for minion in api_ret[key]:
                finger_ret = api.wheel("key.finger", match=minion, hash_type="sha256")[
                    "return"
                ][0]["data"]["return"][key]
                Keys.objects.create(
                    minion_id=minion,
                    status=value,
                    pub=finger_ret[minion],
                )

    return {"result": "refreshed"}


def refresh_minion(minion_id):
    try:
        api = api_connect()
        grain = api.local(minion_id, "grains.items")
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        grain = first_return(grain, "grains.items")
    except SaltApiError as e:
        return {"error": str(e)}
    # TODO: return smt useful, better error mgmt.
    if grain.get(minion_id):
        pillar = api.local(minion_id, "pillar.items")
        pillar = first_return(pillar, "pillar.items")
        minion, _ = Minions.objects.update_or_create(
            minion_id=minion_id,
            defaults={
                "grain": json.dumps(grain[minion_id]),
                "pillar": json.dumps(pillar[minion_id]),
            },
        )
        minion_fields = MinionsCustomFields.objects.values(
            "name", "function"
        ).distinct()
        for field in minion_fields:
            command = RawCommand("salt {} {}".format(minion_id, field["function"]))
            custom_field_return = run_raw(command.parse())
            if "error" in custom_field_return:
                return custom_field_return
            MinionsCustomFields.objects.update_or_create(
                name=field["name"],
                function=field["function"],
                minion=minion,
                defaults={"value": json.dumps(custom_field_return[minion_id])},
            )
    return {"result": "{} refreshed".format(minion_id)}


def refresh_minions_fleet():
    """Refresh every minion's row, in two Salt calls rather than two per minion.

    This used to loop `refresh_minion()` over the fleet: a test.ping to find
    who was alive, then grains.items and pillar.items targeted at one minion at
    a time, plus one call per custom field per minion. On 45 minions that was
    91 jobs for a single page load - and since 3008.13.0 the page refreshes
    itself when it opens, so navigating back to it paid that again.

    One glob-targeted call returns the same data for the whole fleet, and the
    grains response is itself the list of who answered, so the ping is
    redundant as well. Custom fields go the same way: one call per field for
    every minion, rather than per field per minion.

    Returns what the view reports - `refreshed`, `responded`,
    `no_minions_replied`, `source` - or `{"error": ...}`.
    """
    try:
        api = api_connect()
        grains = first_return(api.local("*", "grains.items"), "grains.items")
    except SaltApiError as e:
        return {"error": str(e)}

    if not isinstance(grains, dict):
        return {"error": "unexpected response from grains.items"}

    # A minion that is listed but answered with nothing is not refreshable: its
    # row would be overwritten with an empty grain set.
    answered = {
        minion_id: grain
        for minion_id, grain in grains.items()
        if isinstance(grain, dict) and grain
    }

    if not answered:
        # The master answered and nobody replied. That is usually not an empty
        # fleet: the local client has to read the job back out of the job
        # cache to collect returns, and when that is not being written it
        # gives up with "jid does not exist" and returns nothing. The master's
        # own grain cache needs neither a minion reply nor the job cache, so
        # fall back to it rather than reporting an empty fleet.
        cached = refresh_minions_from_cache()
        if "error" not in cached and cached.get("refreshed"):
            return {
                "refreshed": cached["refreshed"],
                "responded": len(grains),
                "no_minions_replied": True,
                "source": "master cache",
            }
        # Say why the fallback did not help. Swallowing that leaves the same
        # "0 minions refreshed" as a fleet with no minions, with nothing to
        # say the fallback was even attempted.
        return {
            "refreshed": [],
            "responded": len(grains),
            "no_minions_replied": True,
            "source": "none",
            "cache_error": cached.get("error")
            or "the master's grain cache named no minions",
        }

    try:
        pillars = first_return(api.local("*", "pillar.items"), "pillar.items")
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(pillars, dict):
        pillars = {}

    minions = {}
    for minion_id, grain in answered.items():
        pillar = pillars.get(minion_id)
        minion, _ = Minions.objects.update_or_create(
            minion_id=minion_id,
            defaults={
                "grain": json.dumps(grain),
                "pillar": json.dumps(pillar if isinstance(pillar, dict) else {}),
            },
        )
        minions[minion_id] = minion

    for field in MinionsCustomFields.objects.values("name", "function").distinct():
        # shlex strips the quotes; the target reaches Salt as a glob.
        command = RawCommand("salt '*' {}".format(field["function"]))
        values = run_raw(command.parse())
        if "error" in values:
            return values
        for minion_id, minion in minions.items():
            if minion_id not in values:
                continue
            MinionsCustomFields.objects.update_or_create(
                name=field["name"],
                function=field["function"],
                minion=minion,
                defaults={"value": json.dumps(values[minion_id])},
            )

    return {
        "refreshed": sorted(minions),
        "responded": len(grains),
        "no_minions_replied": False,
        "source": "minions",
    }


def refresh_minions_from_cache():
    """Fill the minion table from the master's own data cache.

    `cache.grains` and `cache.pillar` are runners: the master answers them from
    what it already holds, so nothing is published, no minion has to reply, and
    - unlike the local client - the master does not have to read the job back
    out of its job cache. That last point matters, because a job cache that is
    not being written makes every local-client call return nothing at all,
    with the master logging "jid does not exist".

    The data is only as fresh as the master's cache, which is why this is a
    fallback rather than the first choice.
    """
    try:
        api = api_connect()
        # The runner client takes its arguments from `kwarg`; a top level
        # `tgt` is dropped on the floor, and cache.grains with no target
        # returns nothing at all rather than failing.
        grains = first_return(
            api.runner("cache.grains", kwarg={"tgt": "*"}), "cache.grains"
        )
        pillars = first_return(
            api.runner("cache.pillar", kwarg={"tgt": "*"}), "cache.pillar"
        )
    except SaltApiError as e:
        return {"error": str(e)}
    except (KeyError, IndexError, TypeError) as e:
        return {"error": "unexpected response from cache.grains: {}".format(e)}

    if not isinstance(grains, dict):
        return {"error": "the master's grain cache is empty"}

    refreshed = []
    for minion_id, grain in grains.items():
        if not isinstance(grain, dict) or not grain:
            continue
        pillar = pillars.get(minion_id) if isinstance(pillars, dict) else None
        Minions.objects.update_or_create(
            minion_id=minion_id,
            defaults={
                "grain": json.dumps(grain),
                "pillar": json.dumps(pillar if isinstance(pillar, dict) else {}),
            },
        )
        refreshed.append(minion_id)
    return {"refreshed": refreshed}


def run_raw(load):
    try:
        api = api_connect()
        api_ret = api.low(load)
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        return first_return(api_ret, "the Salt API")
    except SaltApiError as e:
        return {"error": str(e)}


def active_jobs():
    """Jobs the master believes are still running, keyed by jid.

    The returner only records a job once it finishes, so a long state run is
    invisible in the job list while it is doing the most damage. This is the
    only view of what is in flight.
    """
    try:
        api = api_connect()
        api_ret = api.runner("jobs.active")
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        return first_return(api_ret, "jobs.active")
    except SaltApiError as e:
        return {"error": str(e)}


def kill_job(jid, target="*", tgt_type="glob", signal="term"):
    """Stop a running job on the minions executing it.

    `term` asks the minion to terminate the process, which lets a state run
    unwind; `kill` is the unconditional version and can leave a half-applied
    state behind. Both are Salt's own saltutil functions - there is no way to
    recall a job that has already been published, only to stop what it started.
    """
    functions = {"term": "saltutil.term_job", "kill": "saltutil.kill_job"}
    if signal not in functions:
        return {"error": "unknown signal {!r}".format(signal)}
    try:
        api = api_connect()
        api_ret = api.local(target, functions[signal], arg=[jid], tgt_type=tgt_type)
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        return first_return(api_ret, functions[signal])
    except SaltApiError as e:
        return {"error": str(e)}


def minion_presence():
    """Which minions are answering the master right now.

    Distinct from "last returned", which is what the minions list shows: a
    minion can be up and healthy while its returns are not being collected,
    and the two look identical from the returner tables alone. manage.status
    pings the fleet and reports up and down separately.
    """
    try:
        api = api_connect()
        api_ret = api.runner("manage.status")
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        status = first_return(api_ret, "manage.status")
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(status, dict):
        return {"error": "manage.status did not return up and down lists"}
    return {
        "up": sorted(status.get("up") or []),
        "down": sorted(status.get("down") or []),
    }


def get_events():
    """The master's event stream.

    Raises SaltApiError when the master cannot be reached. Returning a dict
    here instead meant StreamingHttpResponse iterated its keys and streamed the
    word "error" with a 200, so the status indicator reported a healthy
    connection to a master it had never reached.
    """
    api = api_connect()
    return api.req_stream("/events")


def init_db(target):
    try:
        api = api_connect()
        # Modules.
        modules_func = api.local(target, "sys.list_functions")
        modules_func = modules_func["return"][0][target]

        modules_doc = api.local(target, "sys.doc")

        for func in modules_func:
            desc = modules_doc["return"][0][target][func]

            Functions.objects.update_or_create(
                name=func, type="local", description=desc or ""
            )
        # Runner.
        # TODO: Factorize.
        runner_func = api.local(target, "sys.list_runner_functions")
        runner_func = runner_func["return"][0][target]

        runner_doc = api.local(target, "sys.runner_doc")

        for func in runner_func:
            desc = runner_doc["return"][0][target][func]

            Functions.objects.update_or_create(
                name=func, type="runner", description=desc or ""
            )
        wheel_docs = api.runner("doc.wheel")
        wheel_docs = wheel_docs["return"][0]
        for fun, doc in wheel_docs.items():
            Functions.objects.update_or_create(
                name=fun, type="wheel", description=doc or ""
            )
    except SaltApiError as e:
        return {"error": str(e)}
    return {"result": "refreshed modules using {}".format(target)}


def manage_key(action, target, kwargs):
    try:
        api = api_connect()
        response = api.wheel("key.{}".format(action), match=target, **kwargs)
    except SaltApiError as e:
        return {"error": str(e)}
    return response


def refresh_schedules(minion=None):
    minion = minion or "*"
    try:
        api = api_connect()
        api_ret = api.local(minion, "schedule.list", kwarg={"return_yaml": False})
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        schedules = first_return(api_ret, "schedule.list")
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(schedules, dict):
        return {"error": "schedule.list returned {}".format(type(schedules).__name__)}
    answered = {}
    for minion_id, minion_jobs in schedules.items():
        # A minion the master could not collect a return from is reported as
        # False, not as a mapping of jobs. Iterating that raised TypeError,
        # which surfaced as a Django 500 page rather than as the Salt problem
        # it is - and every minion looks like that when the master cannot read
        # the job back.
        if not isinstance(minion_jobs, dict):
            continue
        answered[minion_id] = minion_jobs
        Schedule.objects.filter(minion=minion_id).delete()
        for job_name in minion_jobs:
            if job_name != "schedule":
                Schedule.objects.create(
                    minion=minion_id,
                    name=job_name,
                    job=json.dumps(minion_jobs[job_name]),
                )
    if schedules and not answered:
        return {
            "error": "{} minion(s) were targeted and none returned their "
            "schedules. The master reported each of them as no-response, "
            "which is what it does when it cannot read the job back from its "
            "job cache.".format(len(schedules))
        }
    return answered


def manage_schedules(action, name, minion):
    try:
        api = api_connect()
        api_ret = api.local(minion, "schedule.{}".format(action), arg=name)
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        results = first_return(api_ret, "schedule.{}".format(action))
    except SaltApiError as e:
        return {"error": str(e)}
    for target in results:
        # If action was successful.
        if results[target]["result"]:
            if "delete" in action:
                Schedule.objects.filter(minion=minion, name=name).delete()
            else:
                try:
                    schedule = Schedule.objects.filter(minion=minion, name=name).get()
                except Schedule.DoesNotExist:
                    # Retry after refreshing schedules for this minion.
                    ret = refresh_schedules(minion)
                    if "error" in ret:
                        return ret
                    try:
                        schedule = Schedule.objects.filter(
                            minion=minion, name=name
                        ).get()
                    except Schedule.DoesNotExist:
                        return False
                loaded_job = schedule.loaded_job()
                if "enable" in action:
                    loaded_job["enabled"] = True
                elif "disable" in action:
                    loaded_job["enabled"] = False
                schedule.job = json.dumps(loaded_job)
                schedule.save()
    return {"result": "ok"}


def refresh_beacons(minion=None):
    """Mirror each minion's beacon configuration into Alcali's table.

    Beacons live on the minion, so this is a read of their state and never a
    source of truth; the table is rebuilt from what answers.
    """
    minion = minion or "*"
    try:
        api = api_connect()
        api_ret = api.local(minion, "beacons.list", kwarg={"return_yaml": False})
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        beacons = first_return(api_ret, "beacons.list")
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(beacons, dict):
        return {"error": "beacons.list returned {}".format(type(beacons).__name__)}

    answered = {}
    for minion_id, minion_beacons in beacons.items():
        # As with schedules, a minion the master could not collect from is
        # reported as False rather than as a mapping.
        if not isinstance(minion_beacons, dict):
            continue
        answered[minion_id] = minion_beacons
        Beacon.objects.filter(minion=minion_id).delete()
        for name, config in minion_beacons.items():
            # beacons.list carries the minion-wide on/off switch in the same
            # mapping as the beacons themselves; it is not one of them.
            if name in ("enabled", "beacons"):
                continue
            Beacon.objects.create(
                minion=minion_id, name=name, config=json.dumps(config)
            )
    if beacons and not answered:
        return {
            "error": "{} minion(s) were targeted and none returned their "
            "beacons. The master reported each of them as no-response, which "
            "is what it does when it cannot read the job back from its job "
            "cache.".format(len(beacons))
        }
    return answered


def manage_beacons(action, name, minion):
    """Enable, disable or delete one beacon on one minion."""
    functions = {
        "delete": "beacons.delete",
        "enable": "beacons.enable_beacon",
        "disable": "beacons.disable_beacon",
    }
    if action not in functions:
        return {"error": "unknown action {!r}".format(action)}
    try:
        api = api_connect()
        api_ret = api.local(minion, functions[action], arg=[name])
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        results = first_return(api_ret, functions[action])
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(results, dict):
        return {"error": "{} returned no result".format(functions[action])}

    # Re-read rather than patching the stored copy: the minion decides what
    # its beacon configuration is, and a partial edit here would drift.
    changed = {
        target: bool(result.get("result"))
        if isinstance(result, dict)
        else bool(result)
        for target, result in results.items()
    }
    if any(changed.values()):
        refreshed = refresh_beacons(minion)
        if isinstance(refreshed, dict) and refreshed.get("error"):
            return refreshed
    return changed


def list_state_files(saltenv="base"):
    """Every .sls the master's file server can serve, as state names.

    The Run page asked people to type a state name from memory with no way to
    check it, and a typo comes back as a Salt error after the job has already
    been published. This is the master's own view of what exists.
    """
    try:
        api = api_connect()
        api_ret = api.runner("fileserver.file_list", kwarg={"saltenv": saltenv})
    except SaltApiError as e:
        return {"error": str(e)}
    try:
        files = first_return(api_ret, "fileserver.file_list")
    except SaltApiError as e:
        return {"error": str(e)}
    if not isinstance(files, list):
        return {"error": "fileserver.file_list returned {}".format(type(files).__name__)}

    states = set()
    for path in files:
        if not isinstance(path, str) or not path.endswith(".sls"):
            continue
        name = path[: -len(".sls")]
        # A directory's init.sls is addressed by the directory name.
        if name.endswith("/init"):
            name = name[: -len("/init")]
        name = name.replace("/", ".")
        # top.sls is the map of what applies where, not something to apply.
        if not name or name == "top":
            continue
        states.add(name)
    return sorted(states)
