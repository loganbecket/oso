"""Urgent changes: what needs to reach the student before the next briefing.

The service cannot write to Google Calendar itself. It records urgent changes and appends them to
`Inbox/Alerts.md`; the alerts skill (a scheduled Cowork task) reads `pending_alerts`, creates the
calendar events through the Calendar connector, and calls `mark_alert_reported`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, time, timedelta

from .config import Config
from .db import EFFECTIVE, now_iso


def pending(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[dict]:
    rows = conn.execute(
        f"""SELECT c.id AS alert_id, c.field, c.old_value, c.new_value, c.detected_at, i.id AS item_id, i.kind, i.url, {EFFECTIVE}
            FROM changes c JOIN items i ON i.id = c.item_id
            WHERE c.urgency = 'urgent' AND c.reported_at IS NULL
            ORDER BY c.detected_at"""
    ).fetchall()
    out = []
    deliver_after = quiet_until(cfg, now)
    muted = {m.lower() for m in cfg.muted_courses}
    for r in rows:
        if (r["course_code"] or "").lower() in muted:
            continue
        course = cfg.course_for(r["course_code"])
        out.append(
            {
                "alert_id": r["alert_id"],
                "item_id": r["item_id"],
                "course": course.name if course else r["course_code"],
                "title": r["title"],
                "kind": r["kind"],
                "message": describe(r),
                "due_at": r["due_at"],
                "url": r["url"],
                "detected_at": r["detected_at"],
                "deliver_after": deliver_after.isoformat(timespec="minutes") if deliver_after else None,
            }
        )
    return out


def describe(r) -> str:
    if r["field"] == "due_at":
        return f"{r['title']} moved from {_fmt(r['old_value'])} to {_fmt(r['new_value'])}"
    if r["field"] == "title":
        return f"'{r['old_value']}' was renamed to '{r['new_value']}'"
    if r["field"] == "deleted":
        return f"{r['title']} was removed from its source"
    return f"{r['title']}: {r['field']} changed"


def mark_reported(conn: sqlite3.Connection, alert_id: int) -> None:
    conn.execute("UPDATE changes SET reported_at = ? WHERE id = ?", (now_iso(), alert_id))


def write_inbox(conn: sqlite3.Connection, cfg: Config, now: datetime) -> int:
    """Append new urgent changes to Inbox/Alerts.md so they are visible in Obsidian even before delivery."""
    rows = conn.execute(
        f"""SELECT c.id, c.field, c.old_value, c.new_value, c.detected_at, {EFFECTIVE}
            FROM changes c JOIN items i ON i.id = c.item_id
            WHERE c.urgency = 'urgent' AND c.detected_at >= ?
            ORDER BY c.detected_at""",
        ((now - timedelta(hours=2)).isoformat(timespec="seconds"),),
    ).fetchall()
    if not rows:
        return 0
    path = cfg.vault / "Inbox" / "Alerts.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else "---\ntype: oso-alerts\n---\n\n# Alerts\n\nUrgent changes Oso noticed. Newest at the bottom.\n"
    added = 0
    for r in rows:
        marker = f"<!-- alert {r['id']} -->"
        if marker in existing:
            continue
        course = cfg.course_for(r["course_code"])
        label = f"**{course.name}**: " if course else ""
        when = datetime.fromisoformat(r["detected_at"]).astimezone(cfg.tz).strftime("%a %b %d %I:%M %p")
        existing += f"\n- {when}: {label}{describe(r)} {marker}"
        added += 1
    if added:
        path.write_text(existing + "\n", encoding="utf-8")
    return added


def quiet_until(cfg: Config, now: datetime) -> datetime | None:
    """If now falls inside quiet hours, the moment they end; otherwise None."""
    if not cfg.quiet_hours or "-" not in cfg.quiet_hours:
        return None
    start_s, end_s = cfg.quiet_hours.split("-", 1)
    start = time.fromisoformat(start_s.strip())
    end = time.fromisoformat(end_s.strip())
    t = now.timetz().replace(tzinfo=None)
    if start <= end:
        inside = start <= t < end
        end_day = now.date()
    else:  # overnight window
        inside = t >= start or t < end
        end_day = now.date() + timedelta(days=1) if t >= start else now.date()
    if not inside:
        return None
    return datetime.combine(end_day, end, tzinfo=now.tzinfo)


def _fmt(iso: str | None) -> str:
    if not iso:
        return "no date"
    try:
        return datetime.fromisoformat(iso).strftime("%a %b %d")
    except ValueError:
        return iso
