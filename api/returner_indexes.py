"""Indexes Alcali needs on Salt's returner tables, and creating them.

Salt's DDL indexes salt_returns by id, jid and fun, and salt_events by tag.
Alcali orders by alter_time on nearly every query and looks up each minion's
state runs by (id, fun), so without these a large history turns the jobs list,
the minions list and the retention counts into full scans and filesorts.

These are Salt's tables and Alcali maps them unmanaged, so no model migration
touches them. This module does it instead, from a migration and from the
`returner_indexes` command, and only ever adds: an index is created only when
no existing one already leads with the same columns, whatever its name, so an
operator's own equivalent index is left alone and never duplicated.

The index names are fixed, because the migration's reverse drops exactly
these and nothing else.
"""

from django.db import DatabaseError

# (name, table, columns). Leading-column order matters: each serves a filter
# on the first columns and an ORDER BY on the next.
RETURNER_INDEXES = (
    # Jobs list, activity graph, retention, the master's keep_jobs pruning.
    ("alcali_ret_alter_time", "salt_returns", ("alter_time",)),
    # A minion's latest return, and when each minion was last heard from.
    ("alcali_ret_id_alter_time", "salt_returns", ("id", "alter_time")),
    # A minion's newest state runs, looked up for every minion on the minions
    # list to judge conformity; also the distinct-minion filter list.
    ("alcali_ret_id_fun_jid", "salt_returns", ("id", "fun", "jid")),
    # Events page and retention.
    ("alcali_evt_alter_time", "salt_events", ("alter_time",)),
)

SUPPORTED_VENDORS = ("mysql", "postgresql", "sqlite")


def _indexed_prefixes(connection, table):
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
    return [
        tuple(c["columns"])
        for c in constraints.values()
        if c.get("index") or c.get("unique") or c.get("primary_key")
    ]


def missing_indexes(connection):
    """The RETURNER_INDEXES entries with no equivalent index yet.

    A table that does not exist is skipped rather than reported: the master
    may simply not be returning to this database, and the diagnostics say so
    separately.
    """
    present = set(connection.introspection.table_names())
    missing = []
    prefixes = {}
    for name, table, columns in RETURNER_INDEXES:
        if table not in present:
            continue
        if table not in prefixes:
            prefixes[table] = _indexed_prefixes(connection, table)
        if not any(existing[: len(columns)] == columns for existing in prefixes[table]):
            missing.append((name, table, columns))
    return missing


def create_sql(connection, name, table, columns):
    qn = connection.ops.quote_name
    cols = ", ".join(qn(c) for c in columns)
    if connection.vendor == "mysql":
        # Online, or not at all: the master writes to these tables on every
        # job return, and an ALTER that fell back to a table lock would stall
        # the returner for as long as the index takes to build. MySQL refuses
        # outright where it cannot honour LOCK=NONE, which is the better
        # failure.
        return "ALTER TABLE {} ADD INDEX {} ({}), ALGORITHM=INPLACE, LOCK=NONE".format(
            qn(table), qn(name), cols
        )
    if connection.vendor == "postgresql":
        # CONCURRENTLY for the same reason; it cannot run inside a
        # transaction, which is why the migration is non-atomic.
        return "CREATE INDEX CONCURRENTLY IF NOT EXISTS {} ON {} ({})".format(
            qn(name), qn(table), cols
        )
    return "CREATE INDEX IF NOT EXISTS {} ON {} ({})".format(qn(name), qn(table), cols)


def drop_sql(connection, name, table):
    qn = connection.ops.quote_name
    if connection.vendor == "mysql":
        return "DROP INDEX {} ON {}".format(qn(name), qn(table))
    if connection.vendor == "postgresql":
        return "DROP INDEX CONCURRENTLY IF EXISTS {}".format(qn(name))
    return "DROP INDEX IF EXISTS {}".format(qn(name))


def ensure_indexes(connection, write=print):
    """Create whatever is missing. Returns (created, failed).

    A failure - usually a database user without INDEX on Salt's tables - is
    reported and skipped rather than raised: the indexes make Alcali faster,
    not correct, and a deployment should not refuse to migrate over them.
    """
    if connection.vendor not in SUPPORTED_VENDORS:
        write("  returner indexes: {} is not supported, skipped".format(connection.vendor))
        return [], []
    created, failed = [], []
    for name, table, columns in missing_indexes(connection):
        label = "{}({})".format(table, ", ".join(columns))
        write(
            "  adding index {} on {} - this reads the whole table and can take "
            "a while on a large history".format(name, label)
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(create_sql(connection, name, table, columns))
        except DatabaseError as exc:
            if connection.vendor == "postgresql":
                # A failed concurrent build leaves an INVALID index behind
                # under this name, which IF NOT EXISTS would then mistake for
                # done on the next attempt.
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(drop_sql(connection, name, table))
                except DatabaseError:
                    pass
            write("  could not add {} on {}: {}".format(name, label, exc))
            failed.append((name, table, columns, str(exc)))
        else:
            created.append((name, table, columns))
    if failed:
        write(
            "  Alcali works without these, only slower. Grant the database user "
            "INDEX on the returner tables and run `alcali returner_indexes "
            "--apply`, or apply docs/returner-indexes.sql by hand."
        )
    return created, failed


def drop_indexes(connection, write=print):
    """Remove the indexes this module names, and only those."""
    if connection.vendor not in SUPPORTED_VENDORS:
        return
    present = set(connection.introspection.table_names())
    for name, table, _columns in RETURNER_INDEXES:
        if table not in present:
            continue
        with connection.cursor() as cursor:
            names = connection.introspection.get_constraints(cursor, table)
        if name not in names:
            continue
        with connection.cursor() as cursor:
            cursor.execute(drop_sql(connection, name, table))
        write("  dropped index {} on {}".format(name, table))
