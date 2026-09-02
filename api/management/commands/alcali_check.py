import os

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import Error as DatabaseError

# Salt's returner tables. Alcali maps them as unmanaged models, so migrate
# never creates them; a deployment whose master is not returning to this
# database has none of them, and every job and event view is silently empty.
SALT_TABLES = ("jids", "salt_returns", "salt_events")

# Alcali orders by alter_time on nearly every query, but Salt's own DDL indexes
# salt_returns only by id, jid and fun, and salt_events only by tag. Without
# these the server scans and filesorts the whole table each time. See
# docs/returner-indexes.sql.
WANTED_INDEX_COLUMNS = {
    "salt_returns": (("alter_time",), ("id", "alter_time")),
    "salt_events": (("alter_time",),),
}

# Alcali's own tables and what fills each one. Jobs and events are read
# straight from the returner, so those views work whether or not the Salt API
# is reachable; everything below is a cache that only a successful sync fills,
# which is why they are the ones that sit empty when the API is misconfigured.
ALCALI_CACHES = (
    ("Minions", "salt_minions", "POST /api/minions/refresh_minions/ (Minions -> refresh)"),
    ("Keys", "salt_keys", "POST /api/keys/refresh/ (Keys -> refresh)"),
    ("Schedule", "api_schedule", "POST /api/schedules/refresh/ (Schedules -> refresh)"),
    ("Functions", "salt_functions", "POST /api/settings/initdb (Settings -> parse modules)"),
)


class Command(BaseCommand):
    help = "Check Alcali's database connection and required environment variables"

    def missing_indexes(self, connection, present_tables):
        """Which of the wanted indexes the returner tables do not have.

        Matched on leading columns rather than by name, because an operator may
        well have created an equivalent index under a different name.
        """
        missing = []
        for table, wanted in WANTED_INDEX_COLUMNS.items():
            if table not in present_tables:
                continue
            try:
                with connection.cursor() as cursor:
                    constraints = connection.introspection.get_constraints(
                        cursor, table
                    )
            except (DatabaseError, NotImplementedError):
                continue
            indexed = [
                tuple(c["columns"])
                for c in constraints.values()
                if c.get("index") or c.get("unique") or c.get("primary_key")
            ]
            for columns in wanted:
                if not any(existing[: len(columns)] == columns for existing in indexed):
                    missing.append("{}({})".format(table, ", ".join(columns)))
        return missing

    def add_arguments(self, parser):
        parser.add_argument(
            "--salt-user",
            help="Log in to the Salt API as this Alcali user, using the token "
            "stored in their settings, and report what happens. This is the "
            "credential the application itself uses.",
        )

    def check_salt_api(self, username):
        """Try the login Alcali performs on every Salt-backed request."""
        from api.backend.salt_api import SaltApiClient, SaltApiError
        from django.contrib.auth.models import User

        url = os.environ.get("SALT_URL", "https://127.0.0.1:8080")
        eauth = os.environ.get("SALT_AUTH", "rest")
        self.stdout.write("salt:\turl {} (eauth {})".format(url, eauth))
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return ["no Alcali user named {}".format(username)]
        token = getattr(getattr(user, "user_settings", None), "token", "")
        if not token:
            return ["{} has no Salt token stored".format(username)]
        if token == "REVOKED":
            return ["{}'s Salt token has been revoked".format(username)]

        api = SaltApiClient(url)
        try:
            login = api.login(username, token, eauth)
        except SaltApiError as exc:
            message = str(exc)
            # By far the most common cause, and the master's own message says
            # nothing about it: Alcali logs in with eauth "rest", which only
            # works if the master has an external_auth: rest block naming this
            # user and pointing ^url back at Alcali's verify endpoint.
            if "401" in message or "Unauthorized" in message:
                message += (
                    "\n\thint: the master must carry, in its own config,\n"
                    "\t  keep_acl_in_token: true\n"
                    "\t  external_auth:\n"
                    "\t    {}:\n"
                    "\t      ^url: <URL at which the master can reach this "
                    "Alcali>/api/token/verify/\n"
                    "\t      {}:\n"
                    "\t        - '.*'\n"
                    "\t        - '@runner'\n"
                    "\t        - '@wheel'\n"
                    "\t        - '@jobs'\n"
                    "\tThe ^url host must also appear in ALLOWED_HOSTS here, "
                    "or Django answers the master with 400.".format(eauth, username)
                )
            return [message]
        perms = login.get("perms")
        self.stdout.write("salt:\tlogin ok as {}, perms {}".format(username, perms))
        if not perms:
            self.stdout.write(
                "warning: the master granted no permissions to {}, so every "
                "Salt-backed action will be refused. Check the eauth block in "
                "the master config.".format(username)
            )
        try:
            keys = api.wheel("key.list_all")["return"][0]["data"]["return"]
        except (SaltApiError, KeyError, IndexError, TypeError) as exc:
            return [
                "logged in, but the wheel client (key.list_all, which fills the "
                "Keys page) failed: {}\n\thint: the master's "
                "netapi_enable_clients must list `wheel`, and this user's ACL "
                "must include '@wheel'.".format(exc)
            ]
        self.stdout.write(
            "salt:\tmaster knows {} accepted key(s)".format(
                len(keys.get("minions") or [])
            )
        )
        try:
            api.local(os.environ.get("MASTER_MINION_ID", "*"), "test.ping")
        except SaltApiError as exc:
            return [
                "wheel works, but the local client (which fills the Minions "
                "page) failed: {}\n\thint: netapi_enable_clients must list "
                "`local`.".format(exc)
            ]
        self.stdout.write("salt:\tlocal client ok")
        return []

    def report_job_cache(self):
        """Is the master writing the job cache, not just the returns?

        `master_job_cache` writes the publish payload to `jids`; the returner
        writes results to `salt_returns`. They are separate writes, and only
        the first is what the master reads back when it collects a job's
        returns. When `jids` is not being written the master logs

            [salt.client][WARNING] jid does not exist

        and gives up on the job immediately, so a Salt-backed action returns an
        empty result with no error - which is what an empty Minions page after
        a refresh that reported success looks like. Alcali reads the same table
        for the Jobs page's User column, so that goes blank too.
        """
        from api.models import Jids, SaltReturns

        problems = []
        try:
            jids = Jids.objects.count()
            returns = SaltReturns.objects.count()
        except DatabaseError as exc:
            self.stdout.write("returner:\tcould not be read: {}".format(exc))
            return problems

        self.stdout.write(
            "returner:\tjids {} row(s), salt_returns {} row(s)".format(jids, returns)
        )
        if not returns:
            return problems

        newest = (
            SaltReturns.objects.order_by("-alter_time")
            .values_list("jid", flat=True)
            .first()
        )
        if newest and not Jids.objects.filter(jid=newest).exists():
            problems.append(
                "the most recent job ({}) has a row in salt_returns but none in "
                "jids, so master_job_cache is not writing".format(newest)
            )
            self.stdout.write(
                "warning: the newest job {} is in salt_returns but not in jids.\n"
                "      The returner is writing results while master_job_cache is\n"
                "      not writing the job cache, so the master cannot read its\n"
                "      own jobs back - it logs 'jid does not exist' and returns\n"
                "      nothing, and refreshing minions or keys finds no minions.\n"
                "      Check that the master's mysql.user/mysql.pass can write\n"
                "      the jids table, and that master_job_cache reached the\n"
                "      running config.".format(newest)
            )
        return problems

    def report_caches(self):
        """Say which of Alcali's own caches are empty, and what fills them."""
        empty = []
        for model_name, table, how in ALCALI_CACHES:
            from django.apps import apps

            model = apps.get_model("api", model_name)
            count = model.objects.count()
            self.stdout.write("cache:\t{:<14} {} row(s)".format(table, count))
            if count == 0:
                empty.append((table, how))
        if empty:
            self.stdout.write(
                "note: these are caches of the master's state, not of the "
                "returner database, so they stay empty until a sync succeeds:"
            )
            for table, how in empty:
                self.stdout.write("      {:<14} filled by {}".format(table, how))
        return empty

    def handle(self, *args, **options):
        required = [
            "MASTER_MINION_ID",
            "DB_BACKEND",
            "DB_NAME",
            "SECRET_KEY",
            "ALLOWED_HOSTS",
            "SALT_URL",
            "SALT_AUTH",
        ]
        if os.environ.get("DB_BACKEND", "sqlite3") != "sqlite3":
            required.extend(["DB_USER", "DB_PASS", "DB_HOST", "DB_PORT"])
        unset = [name for name in required if not os.environ.get(name)]

        connection = connections["default"]
        missing_tables = []
        try:
            connection.cursor()
        except DatabaseError as exc:
            database_error = exc
        else:
            database_error = None
            present = set(connection.introspection.table_names())
            missing_tables = [t for t in SALT_TABLES if t not in present]
            missing_indexes = self.missing_indexes(connection, present)

        self.stdout.write(
            "db:\t{}\nenv:\t{}".format(database_error or "ok", unset or "ok")
        )
        # Reported, but not a failure: a development database has no returner
        # tables and does not need any.
        if missing_tables:
            self.stdout.write(
                "warning: Salt returner tables missing: {}. These are created by "
                "the Salt master's returner, not by migrate; job and event views "
                "stay empty without them.".format(", ".join(missing_tables))
            )

        # Also reported rather than fatal: the application works without these,
        # it just makes the database do far more work than it needs to.
        if missing_indexes:
            self.stdout.write(
                "warning: returner tables are missing indexes Alcali sorts on: "
                "{}. Salt's schema does not create them. Apply "
                "docs/returner-indexes.sql.".format(", ".join(missing_indexes))
            )

        salt_errors = []
        if not database_error:
            self.report_caches()
            self.report_job_cache()
        if options.get("salt_user"):
            salt_errors = self.check_salt_api(options["salt_user"])
            for error in salt_errors:
                self.stdout.write("salt:\tFAILED: {}".format(error))

        # Exit non-zero when something is actually wrong, so this can gate a
        # deployment. A check command that always succeeds cannot be scripted
        # against.
        if database_error or unset or salt_errors:
            raise SystemExit(1)
