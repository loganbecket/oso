"""MCP server over the Oso database and vault, used by the skills in Cowork and Claude Code.

Tool descriptions are kept short on purpose: every one of them sits in Claude's context for every conversation.
"""

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


def _vault_file(cfg: cfgmod.Config, path: str):
    target = (cfg.vault / path).resolve()
    if cfg.vault.resolve() not in target.parents:
        raise ValueError("path must be inside the vault")
    return target


# ---- courses and deadlines ---------------------------------------------------------------------


@mcp.tool()
def list_courses() -> list[dict]:
    """Courses with code, vault folder, and AI policy."""
    with db.connect() as conn:
        return [_row(r) for r in conn.execute("SELECT code, name, folder, ai_policy FROM courses ORDER BY name")]


@mcp.tool()
def add_course(code: str, name: str, folder: str | None = None, ai_policy: str | None = None) -> dict:
    """Register a course (code as Canvas labels it; folder defaults to name)."""
    cfg = _cfg()
    folder = folder or name
    with db.connect() as conn:
        db.upsert_course(conn, code, name, folder, ai_policy)
    cfg.courses = [c for c in cfg.courses if c.code.lower() != code.lower()]
    cfg.courses.append(cfgmod.Course(code=code, name=name, folder=folder))
    cfgmod.save(cfg)
    for sub in ("Lectures", "Homework", "Readings", "Notes", "Exams", "Handwriting"):
        (cfg.vault / "Courses" / folder / sub).mkdir(parents=True, exist_ok=True)
    return {"code": code, "name": name, "folder": f"Courses/{folder}"}


@mcp.tool()
def list_deadlines(days: int = 14, course: str | None = None, include_done: bool = False) -> list[dict]:
    """Open items due within `days` (plus overdue), soonest first."""
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
    """One item in full, with description and source."""
    with db.connect() as conn:
        r = conn.execute(f"SELECT *, {EFFECTIVE} FROM items WHERE id = ?", (item_id,)).fetchone()
    if r is None:
        raise ValueError(f"No item {item_id}")
    return _row(r)


@mcp.tool()
def add_item(course: str, title: str, kind: str, due_at: str | None = None, weight: float | None = None, description: str | None = None) -> dict:
    """Add a confirmed syllabus item. kind: assignment|quiz|exam|reading|event; due_at ISO."""
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
    """Set an item to not_started, started, or done."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_status = ? WHERE id = ?", (status, item_id))
    return {"id": item_id, "status": status}


@mcp.tool()
def set_due_date(item_id: int, due_at: str | None) -> dict:
    """Override an item's due date (ISO), or null to use the source's."""
    cfg = _cfg()
    due = _parse_due(due_at, cfg) if due_at else None
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_due_at = ? WHERE id = ?", (due, item_id))
    return {"id": item_id, "due_at": due}


@mcp.tool()
def set_weight(item_id: int, weight: float | None) -> dict:
    """Set the percent of the course grade an item's category is worth."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_weight = ? WHERE id = ?", (weight, item_id))
    return {"id": item_id, "weight": weight}


@mcp.tool()
def record_grade(item_id: int, points: float, max_points: float) -> dict:
    """Record a received grade."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET grade_points = ?, grade_max = ?, user_status = 'done' WHERE id = ?", (points, max_points, item_id))
    return {"id": item_id, "points": points, "max_points": max_points}


@mcp.tool()
def grade_summary(course: str) -> dict:
    """Standing in a course: percent so far, weight graded and remaining, per category."""
    from . import grades

    with db.connect() as conn:
        return grades.summary(conn, course)


@mcp.tool()
def what_if(course: str, target_percent: float) -> dict:
    """Average needed on remaining work to finish at target_percent."""
    from . import grades

    with db.connect() as conn:
        return grades.what_if(conn, course, target_percent)


# ---- briefing, alerts, health ------------------------------------------------------------------


@mcp.tool()
def today() -> str:
    """Today.md: due today and this week, exams, changes, connection health."""
    cfg = _cfg()
    path = cfg.vault / "Today.md"
    if not path.exists():
        return "Today.md has not been generated yet. Run 'oso sync'."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def pending_alerts() -> list[dict]:
    """Urgent changes not yet delivered, with deliver_after during quiet hours."""
    from . import alerts

    cfg = _cfg()
    with db.connect() as conn:
        return alerts.pending(conn, cfg, datetime.now(cfg.tz))


@mcp.tool()
def mark_alert_reported(alert_id: int) -> dict:
    """Mark an alert as delivered."""
    from . import alerts

    with db.connect() as conn:
        alerts.mark_reported(conn, alert_id)
    return {"alert_id": alert_id, "reported": True}


@mcp.tool()
def health() -> list[dict]:
    """Last sync and last error per source."""
    with db.connect() as conn:
        return [_row(r) for r in db.connector_health(conn)]


# ---- notes -------------------------------------------------------------------------------------


@mcp.tool()
def search_notes(query: str, course: str | None = None, limit: int = 10) -> list[dict]:
    """Full-text search of the vault: path, heading, snippet per hit. Cite the path."""
    from . import index

    with db.connect() as conn:
        return index.search(conn, query, course=course, limit=limit)


@mcp.tool()
def read_note(path: str, start: int = 0, max_chars: int | None = None) -> dict:
    """Read a vault file from `start`. Long files are capped (see `truncated`, `next_start`); prefer read_section."""
    cfg = _cfg()
    text = _vault_file(cfg, path).read_text(encoding="utf-8", errors="replace")
    cap = cfg.read_cap_chars if max_chars is None else max_chars
    if cap and cap > 0 and len(text) - start > cap:
        chunk = text[start:start + cap]
        return {"path": path, "text": chunk, "truncated": True, "next_start": start + cap, "total_chars": len(text)}
    return {"path": path, "text": text[start:], "truncated": False, "next_start": None, "total_chars": len(text)}


@mcp.tool()
def read_section(path: str, heading: str) -> dict:
    """Read just the section under `heading` (as returned by search_notes) of a vault file."""
    from .index import split_sections
    from .notes import read_front_matter

    cfg = _cfg()
    text = _vault_file(cfg, path).read_text(encoding="utf-8", errors="replace")
    _, body = read_front_matter(text)
    want = heading.strip().lower()
    parts = [t for h, t in split_sections(body, max_chars=10**9) if h.strip().lower() == want]
    if not parts:
        return {"path": path, "heading": heading, "text": "", "found": False}
    return {"path": path, "heading": heading, "text": "\n\n".join(parts), "found": True}


@mcp.tool()
def vault_path() -> str:
    """Absolute path of the vault."""
    return str(_cfg().vault)


# ---- handwriting -------------------------------------------------------------------------------


@mcp.tool()
def pending_pages(limit: int = 20) -> list[dict]:
    """Page images waiting for transcription, with notebook and course."""
    from . import handwriting

    with db.connect() as conn:
        return handwriting.pending(conn, limit=limit)


@mcp.tool()
def mark_transcribed(page_path: str, note_path: str, confidence: float) -> dict:
    """Record a transcribed page and its confidence (0 to 1)."""
    from . import handwriting

    with db.connect() as conn:
        handwriting.mark(conn, page_path, note_path, confidence)
    return {"page": page_path, "note": note_path, "confidence": confidence}


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
