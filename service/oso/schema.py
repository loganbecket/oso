"""Every table in Oso's database, applied once per database.

Each module keeps its own `SCHEMA` (the tables it owns) next to the code that uses them; this module is the
one place that runs them all, in dependency order, plus the columns added since a table was first shipped.
`db.connect` calls `apply` on every connection; it returns at once when the database is already current
(`PRAGMA user_version`), so nothing here ever runs in the middle of a sync. Raise VERSION whenever a
`SCHEMA` or the column list below changes, or an installed database will not pick the change up.
"""

from __future__ import annotations

import sqlite3

VERSION = 2

META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"

# Columns added after a table first shipped; `CREATE TABLE IF NOT EXISTS` cannot add them to an existing table.
COLUMNS: dict[str, dict[str, str]] = {
    "items": {"category": "TEXT"},  # the Canvas assignment group (or syllabus category) the item is graded under
    "pages": {"course": "TEXT"},
    "happenings": {"remind": "INTEGER NOT NULL DEFAULT 0"},  # a pop-up when it starts
    "messages": {"pictures": "TEXT"},  # addresses of pictures in a GroupMe message not read yet (JSON list)
}


def current(conn: sqlite3.Connection) -> bool:
    return int(conn.execute("PRAGMA user_version").fetchone()[0]) >= VERSION


def apply(conn: sqlite3.Connection, force: bool = False) -> bool:
    """Create what is missing and add missing columns. True when something was done."""
    if not force and current(conn):
        return False
    from . import canvas_session, canvas_store, classes, db, filing, gcal, groupme, handwriting, happenings, messages, profile, rules, sites, tasks, tutor
    from .connectors import remarkable_usb

    for module in (db, happenings, classes, messages, tasks, rules, profile, tutor, canvas_store, canvas_session, filing, gcal,
                   groupme, handwriting, sites, remarkable_usb):
        conn.executescript(module.SCHEMA)
    conn.executescript(META)
    columns = {**COLUMNS, **profile.COLUMNS}
    for table, cols in columns.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.execute(f"PRAGMA user_version = {VERSION}")
    conn.commit()
    return True
