import binascii
import json
import os
from pathlib import Path

from django.contrib.auth.models import User
from django.db.models import Q

from django.db import models


class FindJobManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(fun="saltutil.find_job")


class Jids(models.Model):
    jid = models.CharField(primary_key=True, db_index=True, max_length=255)
    load = models.TextField()

    def loaded_load(self):
        return json.loads(self.load)

    def user(self):
        if "user" in self.loaded_load():
            return self.loaded_load()["user"]
        return ""

    class Meta:
        managed = False
        db_table = "jids"
        app_label = "api"


class SaltReturns(models.Model):
    fun = models.CharField(max_length=50, db_index=True)
    jid = models.CharField(max_length=255, db_index=True)
    # Field renamed because it was a Python reserved word.
    return_field = models.TextField(db_column="return")
    id = models.CharField(max_length=255, primary_key=True)
    success = models.CharField(max_length=10)
    full_ret = models.TextField()
    alter_time = models.DateTimeField()

    objects = FindJobManager()

    def loaded_ret(self):
        return json.loads(self.full_ret)

    def user(self):
        # TODO: find a better way?
        return Jids.objects.get(jid=self.jid).user()

    def arguments(self):
        ret = self.loaded_ret()
        if "fun_args" in ret and ret["fun_args"]:
            return " ".join(str(i) for i in ret["fun_args"] if "=" not in str(i))
        return ""

    def keyword_arguments(self):
        ret = self.loaded_ret()
        if "fun_args" in ret and ret["fun_args"]:
            return " ".join(str(i) for i in ret["fun_args"] if "=" in str(i))
        return ""

    def success_bool(self):
        """Did this job succeed? None when nothing in the record says so.

        The returner stores ``ret.get("success", False)``, so a false in the
        success column means either "it failed" or "the payload never said".
        It therefore cannot be used to report a failure on its own - only an
        affirmative value there counts for anything.
        """
        ret = self.loaded_ret()
        if isinstance(ret.get("success"), bool):
            return ret["success"]

        payload = ret.get("return")
        if isinstance(payload, dict):
            if isinstance(payload.get("success"), bool):
                return payload["success"]
            if "result" in payload:
                return bool(payload["result"])
            # A state run: each state carries its own result, and one that
            # needed no changes reports None rather than True.
            results = [
                state["result"]
                for state in payload.values()
                if isinstance(state, dict) and "result" in state
            ]
            if results:
                return all(result is not False for result in results)

        # A custom module returning a bare value: retcode is the only verdict.
        if isinstance(ret.get("retcode"), int):
            return ret["retcode"] == 0
        if str(self.success).strip().lower() in {"1", "true", "yes"}:
            return True
        return None

    class Meta:
        managed = False
        db_table = "salt_returns"
        app_label = "api"


class SaltEvents(models.Model):
    id = models.BigAutoField(primary_key=True)
    tag = models.CharField(max_length=255, db_index=True)
    data = models.TextField()
    alter_time = models.DateTimeField()
    master_id = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = "salt_events"
        app_label = "api"


# Alcali custom.
class Functions(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return "{}".format(self.name)

    class Meta:
        db_table = "salt_functions"
        app_label = "api"


class JobTemplate(models.Model):
    name = models.CharField(max_length=255)
    job = models.TextField()

    def __str__(self):
        return "{}".format(self.name)

    class Meta:
        db_table = "salt_job_template"
        app_label = "api"


class Minions(models.Model):
    minion_id = models.CharField(max_length=128, null=False, blank=False)
    grain = models.TextField()
    pillar = models.TextField()

    def loaded_grain(self):
        return json.loads(self.grain)

    def loaded_pillar(self):
        return json.loads(self.pillar)

    def last_job(self):
        return (
            SaltReturns.objects.filter(id=self.minion_id)
            .order_by("-alter_time")
            .first()
        )

    # How far back to look for a highstate. Whether a run counts depends on
    # its arguments, which live inside the JSON payload and cannot be filtered
    # in SQL, so a bounded window is read and examined here.
    HIGHSTATE_SEARCH_DEPTH = 20

    def _state_run_jids(self):
        """The newest state run ids for this minion, newest first.

        Only the ids: a state return carries the whole run in `full_ret`, and
        pulling twenty of those to look at one field each is what made listing
        minions expensive.
        """
        return list(
            SaltReturns.objects.filter(
                Q(fun="state.apply") | Q(fun="state.highstate"), id=self.minion_id
            )
            .order_by("-jid")
            .values_list("jid", flat=True)[: self.HIGHSTATE_SEARCH_DEPTH]
        )

    def _compute_last_highstate(self, jids=None):
        # Newest first. This used to take the two most recent state runs and
        # then re-sort them oldest-first before returning the first match, so
        # "last highstate" was really the one before last: a minion whose most
        # recent highstate passed still reported the previous failure.
        #
        # A run with arguments is a targeted state, not a highstate; a test run
        # still describes the minion's conformity. Rows are pulled one at a
        # time because the first is almost always the answer, and each one
        # parsed is a full run's worth of JSON.
        for jid in self._state_run_jids() if jids is None else jids:
            state = SaltReturns.objects.filter(jid=jid, id=self.minion_id).first()
            if state is None:
                continue
            try:
                fun_args = state.loaded_ret().get("fun_args") or []
            except ValueError:
                continue
            if (
                not fun_args
                or fun_args[0] == {"test": True}
                or fun_args[0] == "test=True"
            ):
                return state
        return None

    @staticmethod
    def _verdict_for(highstate):
        """Whether a highstate return describes a conformant minion."""
        if not highstate:
            return None
        try:
            highstate_ret = highstate.loaded_ret()
        except ValueError:
            return False

        # Flat out error(return is a string)
        return_item = highstate_ret.get("return")
        if not return_item or isinstance(return_item, list):
            return False

        for result in return_item.values():
            # Not every entry is guaranteed to be a state result mapping: a
            # module that returns a bare value puts a string or a list here,
            # and calling .get on it raised AttributeError - a 500 for the
            # whole minions list rather than one odd state.
            if not isinstance(result, dict):
                return False
            # A state reports None when it made no changes but would have,
            # which is a highstate that has drifted, not one that passed.
            if not result.get("result"):
                return False
        return True

    def conformity_entry(self):
        """The stored verdict, recomputed only when a newer state run exists.

        Memoised per instance as well: the serializer asks for the verdict and
        for the highstate time, and both come from here.
        """
        if hasattr(self, "_conformity_entry_cache"):
            return self._conformity_entry_cache

        jids = self._state_run_jids()
        newest = jids[0] if jids else ""
        entry = ConformityCache.objects.filter(minion_id=self.minion_id).first()
        if entry is None or entry.source_jid != newest:
            highstate = self._compute_last_highstate(jids)
            entry, _ = ConformityCache.objects.update_or_create(
                minion_id=self.minion_id,
                defaults={
                    "source_jid": newest,
                    "verdict": self._verdict_for(highstate),
                    "highstate_jid": highstate.jid if highstate else "",
                    "highstate_time": highstate.alter_time if highstate else None,
                },
            )
        self._conformity_entry_cache = entry
        return entry

    def last_highstate(self):
        # Memoised: kept returning the return itself for callers that want the
        # run, while the minions list reads the cached time instead.
        if not hasattr(self, "_last_highstate_cache"):
            jid = self.conformity_entry().highstate_jid
            self._last_highstate_cache = (
                SaltReturns.objects.filter(jid=jid, id=self.minion_id).first()
                if jid
                else None
            )
        return self._last_highstate_cache

    def last_highstate_time(self):
        return self.conformity_entry().highstate_time

    def conformity(self):
        return self.conformity_entry().verdict

    def custom_conformity(self, fun, *args):
        # First, filter with fun.
        jobs = SaltReturns.objects.filter(fun=fun, id=self.minion_id).order_by(
            "-alter_time"
        )
        if not jobs:
            return False
        if args:
            for job in jobs:
                ret = job.loaded_ret()
                # if provided args are the same.
                if not list(
                    set(args) ^ {i for i in ret["fun_args"] if isinstance(i, str)}
                ):
                    return ret["return"]
        # If no args or kwargs, just return the first job.
        else:
            job = jobs.first()
            return job.loaded_ret()["return"]

    def __str__(self):
        return "{}".format(self.minion_id)

    class Meta:
        db_table = "salt_minions"
        app_label = "api"


class Keys(models.Model):
    KEY_STATUS = (
        ("accepted", "accepted"),
        ("rejected", "rejected"),
        ("denied", "denied"),
        ("unaccepted", "unaccepted"),
    )
    minion_id = models.CharField(max_length=255)
    pub = models.TextField(blank=True)
    status = models.CharField(max_length=64, choices=KEY_STATUS)

    def __str__(self):
        return "{}".format(self.minion_id)

    class Meta:
        # TODO add constraints (only one accepted per minion_id)
        db_table = "salt_keys"
        app_label = "api"


class MinionsCustomFields(models.Model):
    name = models.CharField(max_length=255)
    value = models.TextField()
    minion = models.ForeignKey(
        Minions, related_name="custom_fields", on_delete=models.CASCADE
    )
    function = models.CharField(max_length=255)

    def __str__(self):
        return "{}: {}".format(self.name, self.function)

    class Meta:
        db_table = "minions_custom_fields"
        app_label = "api"


class Schedule(models.Model):
    minion = models.CharField(max_length=128, null=False, blank=False)
    name = models.CharField(max_length=255, blank=False, null=False)
    job = models.TextField()

    def loaded_job(self):
        return json.loads(self.job)

    class Meta:
        app_label = "api"


class Beacon(models.Model):
    """A minion-side beacon, as reported by beacons.list.

    The direct sibling of Schedule, and kept the same shape deliberately:
    both are minion-local configuration that Alcali mirrors rather than owns,
    refreshed from the minion and never treated as the source of truth.
    """

    minion = models.CharField(max_length=128, null=False, blank=False)
    name = models.CharField(max_length=255, blank=False, null=False)
    config = models.TextField()

    def loaded_config(self):
        return json.loads(self.config)

    def enabled(self):
        """Beacons report their own enabled flag inside the config list.

        beacons.list gives each beacon as a list of single-key mappings, one
        of which may be {"enabled": bool}. Absent means enabled.
        """
        try:
            entries = self.loaded_config()
        except ValueError:
            return True
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return True
        for entry in entries:
            if isinstance(entry, dict) and "enabled" in entry:
                return bool(entry["enabled"])
        return True

    def __str__(self):
        return "{}:{}".format(self.minion, self.name)

    class Meta:
        app_label = "api"


def generate_key():
    return binascii.hexlify(os.urandom(20)).decode()


def default_user_settings():
    settings_path = Path(__file__).parent / "migrations" / "usersettings.json"
    with settings_path.open(encoding="utf-8") as fh:
        return json.load(fh)


class UserSettings(models.Model):
    """
    The default authorization token model.
    """

    user = models.OneToOneField(
        User, primary_key=True, related_name="user_settings", on_delete=models.CASCADE
    )
    token = models.CharField(max_length=40)
    created = models.DateTimeField(auto_now_add=True)
    settings = models.JSONField(default=default_user_settings)
    salt_permissions = models.TextField()

    def generate_token(self):
        self.token = generate_key()
        self.save()

    class Meta:
        db_table = "user_settings"
        app_label = "api"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = generate_key()
        return super(UserSettings, self).save(*args, **kwargs)

    def __str__(self):
        return str(self.user)


class Conformity(models.Model):
    name = models.CharField(max_length=255)
    function = models.CharField(max_length=255)

    class Meta:
        db_table = "conformity"
        app_label = "api"


class ConformityCache(models.Model):
    """The last computed highstate verdict for a minion.

    Deriving conformity means JSON-parsing `full_ret`, and a real highstate is
    hundreds of states - a megabyte or so per minion, parsed on every request
    that lists minions. The verdict can only change when a newer state run
    lands, so it is stored against the newest run seen and recomputed only
    when that moves.

    This is Alcali's own table: the returner tables are Salt's and unmanaged.
    Losing it costs a recomputation, nothing more.
    """

    minion_id = models.CharField(max_length=128, unique=True)
    # Invalidation key: the newest state run for this minion when the verdict
    # was computed, whether or not that run is the one it was computed from.
    source_jid = models.CharField(max_length=255)
    # True conformant, False drifted, null no highstate to judge.
    verdict = models.BooleanField(null=True)
    # The run the verdict came from, for the "last highstate" column.
    highstate_jid = models.CharField(max_length=255, blank=True)
    highstate_time = models.DateTimeField(null=True, blank=True)
    computed = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{}: {}".format(self.minion_id, self.verdict)

    class Meta:
        db_table = "alcali_conformity_cache"
        app_label = "api"


class AuditLog(models.Model):
    """What Alcali itself was asked to change, and by whom.

    Anything Alcali delegates to the master is recorded by Salt in `jids`, so
    it can be traced there. Its own records - deleting a minion, editing a job
    template, changing a conformity rule or a user - never reached Salt and so
    left no trace anywhere.
    """

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    # Kept alongside the FK so the record survives the user being deleted.
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return "{} {} {}".format(self.username or "-", self.action, self.target)

    class Meta:
        db_table = "alcali_audit_log"
        app_label = "api"
        ordering = ("-created",)
