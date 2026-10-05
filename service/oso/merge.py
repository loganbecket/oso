"""Merge what connectors saw into the database and record what changed.

Rules:
- An item is identified by (source, external_id). Seen again, its source fields update.
- Changes to due date or title are recorded in `changes` with an urgency.
- Items a source no longer returns are marked deleted, never removed.
- The same thing seen from two sources (same course, same normalized title, due the same day)
  is linked by `merged_into` so it appears once.
- user_* columns are never written here.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

from .db import Item, now_iso

URGENT_WINDOW = timedelta(days=7)


def apply(conn: sqlite3.Connection, items: list[Item], source: str, now: datetime, urgent_days: int = 7) -> dict[str, int]:
    seen_ids: list[str] = []
    counts = {"new": 0, "updated": 0, "changed": 0, "deleted": 0}
    ts = now_iso()
    for it in items:
        seen_ids.append(it.external_id)
        row = conn.execute(
            "SELECT * FROM items WHERE source = ? AND external_id = ?", (source, it.external_id)
        ).fetchone()
        due = it.due_at.isoformat(timespec="minutes") if it.due_at else None
        if row is None:
            cur = conn.execute(
                """INSERT INTO items (source, external_id, course_code, kind, title, due_at, all_day, url,
                                      description, weight, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source, it.external_id, it.course_code, it.kind, it.title, due, int(it.all_day), it.url,
                 it.description, it.weight, ts, ts),
            )
            counts["new"] += 1
            _link_duplicate(conn, int(cur.lastrowid), it, due)
            continue

        changed = False
        for field, new in (("due_at", due), ("title", it.title)):
            old = row[field]
            if old != new:
                conn.execute(
                    "INSERT INTO changes (item_id, field, old_value, new_value, detected_at, urgency) VALUES (?, ?, ?, ?, ?, ?)",
                    (row["id"], field, old, new, ts, _urgency(field, row["kind"], it.due_at, now, timedelta(days=urgent_days))),
                )
                changed = True
        conn.execute(
            """UPDATE items SET course_code = ?, kind = ?, title = ?, due_at = ?, all_day = ?, url = ?,
                                description = ?, weight = COALESCE(?, weight), last_seen = ?, deleted_at = NULL
               WHERE id = ?""",
            (it.course_code, it.kind, it.title, due, int(it.all_day), it.url, it.description, it.weight, ts, row["id"]),
        )
        counts["updated"] += 1
        if changed:
            counts["changed"] += 1

    # Anything this source used to return and no longer does.
    seen = set(seen_ids)
    gone = [
        r for r in conn.execute(
            "SELECT id, external_id FROM items WHERE source = ? AND deleted_at IS NULL", (source,)
        ).fetchall()
        if r["external_id"] not in seen
    ]
    for g in gone:
        conn.execute("UPDATE items SET deleted_at = ? WHERE id = ?", (ts, g["id"]))
        conn.execute(
            "INSERT INTO changes (item_id, field, old_value, new_value, detected_at, urgency) VALUES (?, 'deleted', NULL, ?, ?, 'routine')",
            (g["id"], ts, ts),
        )
        counts["deleted"] += 1
    return counts


def _urgency(field: str, kind: str, due_at: datetime | None, now: datetime, window: timedelta = URGENT_WINDOW) -> str:
    if field == "due_at" and kind == "exam":
        return "urgent"
    if field == "due_at" and due_at is not None and due_at - now <= window:
        return "urgent"
    return "routine"


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\b(hw|homework|assignment|due|the|a|an)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _link_duplicate(conn: sqlite3.Connection, new_id: int, it: Item, due: str | None) -> None:
    """If another source already has this item, point the new row at it."""
    if not it.course_code or not due:
        return
    day = due[:10]
    norm = normalize_title(it.title)
    for row in conn.execute(
        """SELECT id, title FROM items
           WHERE id != ? AND source != ? AND merged_into IS NULL AND deleted_at IS NULL
             AND course_code = ? AND substr(due_at, 1, 10) = ?""",
        (new_id, it.source, it.course_code, day),
    ).fetchall():
        if normalize_title(row["title"]) == norm:
            conn.execute("UPDATE items SET merged_into = ? WHERE id = ?", (row["id"], new_id))
            return
