"""MCP server over the Oso database and vault, used by the skills in Cowork and Claude Code."""

from __future__ import annotations

from datetime import datetime, timedelta

from mcp.server.mcpserver import MCPServer

from . import config as cfgmod
from . import db
from .db import EFFECTIVE

mcp = MCPServer("oso")

STATUSES = ("not_started", "started", "done")
KINDS = ("assignment", "quiz", "exam", "reading", "event")


def _cfg() -> cfgmod.Config:
    return cfgmod.load()


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


@mcp.tool()
def list_courses() -> list[dict]:
    """Every course Oso knows, with its vault folder and AI policy."""
    with db.connect() as conn:
        return [_row(r) for r in conn.execute("SELECT code, name, folder, ai_policy FROM courses ORDER BY name")]


@mcp.tool()
def add_course(code: str, name: str, folder: str | None = None, ai_policy: str | None = None) -> dict:
    """Register a course. code is how Canvas labels it (e.g. MATH-101-001); folder is the vault folder (defaults to name)."""
    cfg = _cfg()
    folder = folder or name
    with db.connect() as conn:
        db.upsert_course(conn, code, name, folder, ai_policy)
    cfg.courses = [c for c in cfg.courses if c.code.lower() != code.lower()]
    cfg.courses.append(cfgmod.Course(code=code, name=name, folder=folder))
    cfgmod.save(cfg)
    for sub in ("Lectures", "Homework", "Readings", "Notes", "Exams"):
        (cfg.vault / "Courses" / folder / sub).mkdir(parents=True, exist_ok=True)
    return {"code": code, "name": name, "folder": f"Courses/{folder}"}


@mcp.tool()
def list_deadlines(days: int = 14, course: str | None = None, include_done: bool = False) -> list[dict]:
    """Open items due within the next `days` days (plus anything overdue), soonest first. course filters by code."""
    cfg = _cfg()
    now = datetime.now(cfg.tz)
    horizon = (now + timedelta(days=days)).isoformat(timespec="minutes")
    sql = f"""SELECT id, kind, source, url, {EFFECTIVE} FROM items
              WHERE deleted_at IS NULL AND merged_into IS NULL AND (due_at IS NULL OR COALESCE(user_due_at, due_at) <= ?)"""
    params: list = [horizon]
    if course:
        sql += " AND COALESCE(user_course, course_code) = ?"
        params.append(course)
    sql += " ORDER BY COALESCE(user_due_at, due_at)"
    with db.connect() as conn:
        rows = [_row(r) for r in conn.execute(sql, params)]
    if not include_done:
        rows = [r for r in rows if r["status"] != "done"]
    return rows


@mcp.tool()
def get_item(item_id: int) -> dict:
    """Full detail for one item, including its description and source."""
    with db.connect() as conn:
        r = conn.execute(f"SELECT *, {EFFECTIVE} FROM items WHERE id = ?", (item_id,)).fetchone()
    if r is None:
        raise ValueError(f"No item {item_id}")
    return _row(r)


@mcp.tool()
def add_item(course: str, title: str, kind: str, due_at: str | None = None, weight: float | None = None, description: str | None = None) -> dict:
    """Add an item the student confirmed from a syllabus. kind: assignment, quiz, exam, reading, event. due_at: ISO date or datetime."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    cfg = _cfg()
    due = _parse_due(due_at, cfg) if due_at else None
    ts = db.now_iso()
    ext = f"{course}:{kind}:{title}:{due[:10] if due else ''}"
    with db.connect() as conn:
        cur = conn.execute(
            """INSERT INTO items (source, external_id, course_code, kind, title, due_at, all_day, description, weight, first_seen, last_seen)
               VALUES ('syllabus', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, external_id) DO UPDATE SET due_at = excluded.due_at, weight = excluded.weight,
                 description = excluded.description, last_seen = excluded.last_seen, deleted_at = NULL""",
            (ext, course, kind, title, due, int(bool(due) and len(due_at or "") <= 10), description, weight, ts, ts),
        )
        item_id = cur.lastrowid
    return {"id": item_id, "course": course, "title": title, "kind": kind, "due_at": due, "weight": weight}


@mcp.tool()
def update_status(item_id: int, status: str) -> dict:
    """Mark an item not_started, started, or done. This is the student's call and survives syncs."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_status = ? WHERE id = ?", (status, item_id))
    return {"id": item_id, "status": status}


@mcp.tool()
def set_due_date(item_id: int, due_at: str | None) -> dict:
    """Override an item's due date (ISO date or datetime), or pass null to go back to what the source says."""
    cfg = _cfg()
    due = _parse_due(due_at, cfg) if due_at else None
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_due_at = ? WHERE id = ?", (due, item_id))
    return {"id": item_id, "due_at": due}


@mcp.tool()
def record_grade(item_id: int, points: float, max_points: float) -> dict:
    """Record a grade the student received on an item."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET grade_points = ?, grade_max = ?, user_status = 'done' WHERE id = ?", (points, max_points, item_id))
    return {"id": item_id, "points": points, "max_points": max_points}


@mcp.tool()
def today() -> str:
    """The current Today.md: due today, due this week, exams, changes since yesterday, and connection health."""
    cfg = _cfg()
    path = cfg.vault / "Today.md"
    if not path.exists():
        return "Today.md has not been generated yet. Run 'oso sync' on the laptop."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def health() -> list[dict]:
    """When each source last synced and whether it is failing."""
    with db.connect() as conn:
        return [_row(r) for r in db.connector_health(conn)]


def _parse_due(value: str, cfg: cfgmod.Config) -> str:
    dt = datetime.fromisoformat(value)
    if len(value) <= 10:
        dt = dt.replace(hour=23, minute=59)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=cfg.tz)
    return dt.isoformat(timespec="minutes")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


# ---- notes and handwriting -------------------------------------------------------------------


@mcp.tool()
def search_notes(query: str, course: str | None = None, limit: int = 10) -> list[dict]:
    """Full-text search over the student's vault. Returns path, heading, and a snippet per hit; cite the path."""
    from . import index

    with db.connect() as conn:
        return index.search(conn, query, course=course, limit=limit)


@mcp.tool()
def read_note(path: str) -> str:
    """Read one vault file by its path relative to the vault root (as returned by search_notes)."""
    cfg = _cfg()
    target = (cfg.vault / path).resolve()
    if cfg.vault.resolve() not in target.parents and target != cfg.vault.resolve():
        raise ValueError("path must be inside the vault")
    return target.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def pending_pages(limit: int = 20) -> list[dict]:
    """Handwritten page images waiting to be transcribed, as vault-relative paths grouped by notebook."""
    from . import handwriting

    with db.connect() as conn:
        return handwriting.pending(conn, limit=limit)


@mcp.tool()
def mark_transcribed(page_path: str, note_path: str, confidence: float) -> dict:
    """Record that a page image was transcribed into note_path, with confidence from 0 to 1."""
    from . import handwriting

    with db.connect() as conn:
        handwriting.mark(conn, page_path, note_path, confidence)
    return {"page": page_path, "note": note_path, "confidence": confidence}


@mcp.tool()
def vault_path() -> str:
    """The absolute path of the Obsidian vault on this machine."""
    return str(_cfg().vault)


# ---- alerts and grades -------------------------------------------------------------------------


@mcp.tool()
def pending_alerts() -> list[dict]:
    """Urgent changes not yet delivered: moved due dates, rescheduled exams, new items due soon. Each has a message, the item's due_at, and deliver_after (set during quiet hours)."""
    from . import alerts

    cfg = _cfg()
    with db.connect() as conn:
        return alerts.pending(conn, cfg, datetime.now(cfg.tz))


@mcp.tool()
def mark_alert_reported(alert_id: int) -> dict:
    """Record that an alert reached the student (for example, a calendar event was created for it)."""
    from . import alerts

    with db.connect() as conn:
        alerts.mark_reported(conn, alert_id)
    return {"alert_id": alert_id, "reported": True}


@mcp.tool()
def grade_summary(course: str) -> dict:
    """Current standing in a course: percent so far, weight graded, weight remaining, and each category's score."""
    from . import grades

    with db.connect() as conn:
        return grades.summary(conn, course)


@mcp.tool()
def what_if(course: str, target_percent: float) -> dict:
    """The average needed on everything still ungraded to finish the course at target_percent."""
    from . import grades

    with db.connect() as conn:
        return grades.what_if(conn, course, target_percent)


@mcp.tool()
def set_weight(item_id: int, weight: float | None) -> dict:
    """Set the percentage of the course grade an item's category is worth (the student's override)."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_weight = ? WHERE id = ?", (weight, item_id))
    return {"id": item_id, "weight": weight}
