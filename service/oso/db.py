"""SQLite store for courses, items, sync health, and detected changes.

Facts from sources live in the plain columns. Anything the student changes by hand
lives in the user_* columns and always wins; syncs never touch them.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

from .config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    folder      TEXT NOT NULL,
    ai_policy   TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    course_code   TEXT,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    due_at        TEXT,
    all_day       INTEGER NOT NULL DEFAULT 0,
    url           TEXT,
    description   TEXT,
    weight        REAL,
    category      TEXT,
    status        TEXT NOT NULL DEFAULT 'not_started',
    grade_points  REAL,
    grade_max     REAL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    deleted_at    TEXT,
    merged_into   INTEGER REFERENCES items(id),
    user_title    TEXT,
    user_due_at   TEXT,
    user_status   TEXT,
    user_weight   REAL,
    user_course   TEXT,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY,
    connector   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER,
    error       TEXT,
    items_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS changes (
    id           INTEGER PRIMARY KEY,
    item_id      INTEGER NOT NULL REFERENCES items(id),
    field        TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    detected_at  TEXT NOT NULL,
    urgency      TEXT NOT NULL DEFAULT 'routine',
    reported_at  TEXT
);

-- The last failure of each step of a check (books, search, profiles, ...), cleared when the step next succeeds,
-- so a silent breakage reaches Today.md and the health check.
CREATE TABLE IF NOT EXISTS step_failures (
    name   TEXT PRIMARY KEY,
    at     TEXT NOT NULL,
    error  TEXT NOT NULL
);
"""


def db_path() -> Path:
    return data_dir() / "oso.sqlite"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def fmt_day(iso: str | None) -> str:
    """An ISO moment as 'Mon Oct 05', or 'no date'."""
    if not iso:
        return "no date"
    try:
        return datetime.fromisoformat(iso).strftime("%a %b %d")
    except ValueError:
        return iso


def since(now: datetime, delta: timedelta) -> str:
    """The moment `delta` before `now`, as the UTC text every `*_at` column stores, so a window compares correctly
    whatever the student's time zone (an ISO string with a local offset does not sort against a UTC one)."""
    return (now - delta).astimezone(UTC).isoformat(timespec="seconds")


BUSY_SECONDS = 30  # a check and a Claude conversation share the database; the second waits instead of failing


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    from . import schema

    conn = sqlite3.connect(str(path or db_path()), timeout=BUSY_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # readers and one writer at the same time
    schema.apply(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def open_items(conn: sqlite3.Connection) -> list[dict]:
    """Every item not done, with the student's edits applied, soonest first: what Today.md and readiness list."""
    rows = conn.execute(
        f"""SELECT id, kind, url, {EFFECTIVE} FROM items
            WHERE deleted_at IS NULL AND merged_into IS NULL
            ORDER BY due_at"""
    ).fetchall()
    out = []
    for r in rows:
        if r["status"] == "done":
            continue
        due = datetime.fromisoformat(r["due_at"]) if r["due_at"] else None
        out.append({"id": r["id"], "kind": r["kind"], "title": r["title"], "due": due, "status": r["status"],
                    "weight": r["weight"], "course_code": r["course_code"], "url": r["url"]})
    return out




def prune(conn: sqlite3.Connection, now: datetime, keep_days: int = 180) -> int:
    """Forget change records and Canvas events older than a term, so the tables stop growing forever."""
    cutoff = since(now, timedelta(days=keep_days))
    n = conn.execute("DELETE FROM changes WHERE detected_at < ?", (cutoff,)).rowcount
    try:
        n += conn.execute("DELETE FROM canvas_events WHERE at < ?", (cutoff,)).rowcount
    except sqlite3.OperationalError:
        pass
    return n


def note_step_failure(conn: sqlite3.Connection, name: str, error: str) -> None:
    conn.execute("INSERT OR REPLACE INTO step_failures (name, at, error) VALUES (?, ?, ?)", (name, now_iso(), error))


def clear_step_failure(conn: sqlite3.Connection, name: str) -> None:
    conn.execute("DELETE FROM step_failures WHERE name = ?", (name,))


def step_failures(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT name, at, error FROM step_failures ORDER BY name").fetchall()


@dataclass
class Item:
    """An assignment, quiz, exam, reading, or event as a connector sees it."""

    source: str
    external_id: str
    kind: str
    title: str
    due_at: datetime | None
    all_day: bool = False
    course_code: str | None = None
    url: str | None = None
    description: str | None = None
    weight: float | None = None
    category: str | None = None  # the grading category (Canvas assignment group) it belongs to


# Effective values: the student's edits win over the source's.
EFFECTIVE = """
    COALESCE(user_title, title)       AS title,
    COALESCE(user_due_at, due_at)     AS due_at,
    COALESCE(user_status, status)     AS status,
    COALESCE(user_weight, weight)     AS weight,
    COALESCE(user_course, course_code) AS course_code
"""


def upsert_course(conn: sqlite3.Connection, code: str, name: str, folder: str, ai_policy: str | None = None) -> None:
    conn.execute(
        """INSERT INTO courses (code, name, folder, ai_policy, created_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(code) DO UPDATE SET name = excluded.name, folder = excluded.folder,
             ai_policy = COALESCE(excluded.ai_policy, courses.ai_policy)""",
        (code, name, folder, ai_policy, now_iso()),
    )


def record_sync(conn: sqlite3.Connection, connector: str) -> int:
    cur = conn.execute("INSERT INTO sync_runs (connector, started_at) VALUES (?, ?)", (connector, now_iso()))
    return int(cur.lastrowid)


def finish_sync(conn: sqlite3.Connection, run_id: int, ok: bool, error: str | None = None, items_seen: int = 0) -> None:
    conn.execute(
        "UPDATE sync_runs SET finished_at = ?, ok = ?, error = ?, items_seen = ? WHERE id = ?",
        (now_iso(), int(ok), error, items_seen, run_id),
    )


def connector_health(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Latest run per connector, plus the last successful one."""
    return conn.execute(
        """
        SELECT r.connector,
               r.finished_at AS last_run,
               r.ok          AS last_ok,
               r.error       AS last_error,
               (SELECT MAX(finished_at) FROM sync_runs s WHERE s.connector = r.connector AND s.ok = 1) AS last_success
        FROM sync_runs r
        WHERE r.id = (SELECT MAX(id) FROM sync_runs s2 WHERE s2.connector = r.connector)
        ORDER BY r.connector
        """
    ).fetchall()
