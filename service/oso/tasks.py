"""Tasks: his checklist of things to get done (laundry, an oil change, registering to vote), kept by Oso and shown
on his phone as an "Oso" list in Google Tasks.

He adds a task by telling Claude, or in Google Tasks itself; things to do that Claude picks out of school email,
GroupMe, and Canvas join the list too. Most tasks have a day they should be done by and no time: they get moved
around, and the briefing suggests which fit today's free time. A reminder at a moment ("when class lets out") is a
pop-up event on the Oso calendar instead (`add_to_calendar` with remind).

The list in Oso and the one in Google Tasks are kept the same on every check: what he checks off, adds, renames,
or deletes on his phone comes back, and what Claude changes goes out. When both changed the same task since the
last check, the newer change wins. Without Google Tasks connected the list still works, through Claude and the
briefing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, date, datetime, time, timedelta

from . import happenings, secrets
from .config import Config

log = logging.getLogger("oso.tasks")

SCOPES = ["https://www.googleapis.com/auth/tasks"]
API = "https://tasks.googleapis.com/tasks/v1"
TOKEN = "google_tasks_token"
LIST_ID = "google_tasks_list"
LIST_NAME = "Oso"
DONE_SHOWN = timedelta(hours=36)  # checked-off tasks the briefing mentions

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    notes       TEXT,
    due         TEXT,                       -- YYYY-MM-DD, the day it should be done by; none for whenever
    status      TEXT NOT NULL DEFAULT 'open',  -- open, done, deleted
    source      TEXT NOT NULL,              -- chat, google (added on his phone), email, groupme, canvas
    happening   INTEGER UNIQUE,             -- the action it came from, when Claude picked it out of a message
    google_id   TEXT UNIQUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,              -- the last change made in Oso
    pushed_at   TEXT,                       -- the last time Google Tasks was brought up to date with it
    done_at     TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class NotConnected(Exception):
    pass


def _ts() -> str:
    """Now, to the microsecond: a change made in the same second as the last push must still count as newer."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    happenings.ensure(conn)


# ---- the list ------------------------------------------------------------------------------------------------


def _day(value: str | None) -> str | None:
    return date.fromisoformat(value[:10]).isoformat() if value else None


def add(conn: sqlite3.Connection, title: str, due: str | None = None, notes: str | None = None, source: str = "chat",
        happening: int | None = None) -> int | None:
    """Add a task. None when the same open task is already on the list."""
    ensure(conn)
    title = (title or "").strip()[:300]
    if not title:
        raise ValueError("A task needs a name.")
    for r in conn.execute("SELECT id, title FROM tasks WHERE status = 'open'"):
        if happenings._norm(r["title"]) == happenings._norm(title):
            return None
    ts = _ts()
    cur = conn.execute(
        "INSERT INTO tasks (title, notes, due, source, happening, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, (notes or "").strip() or None, _day(due), source, happening, ts, ts),
    )
    return int(cur.lastrowid)


def find(conn: sqlite3.Connection, task: int | str) -> sqlite3.Row | None:
    ensure(conn)
    if isinstance(task, int) or str(task).isdigit():
        return conn.execute("SELECT * FROM tasks WHERE id = ? AND status != 'deleted'", (int(task),)).fetchone()
    key = happenings._norm(str(task))
    rows = [r for r in conn.execute("SELECT * FROM tasks WHERE status != 'deleted' ORDER BY status = 'open' DESC, id DESC")
            if key and key in happenings._norm(r["title"])]
    return rows[0] if rows else None


def change(conn: sqlite3.Connection, task: int | str, *, title: str | None = None, due: str | None = None,
           clear_due: bool = False, notes: str | None = None, done: bool | None = None, delete: bool = False) -> str:
    row = find(conn, task)
    if row is None:
        return f"There's no task like {task!r} on his list."
    ts = _ts()
    if delete:
        conn.execute("UPDATE tasks SET status = 'deleted', updated_at = ? WHERE id = ?", (ts, row["id"]))
        return f"Took \"{row['title']}\" off the list."
    status = row["status"] if done is None else ("done" if done else "open")
    conn.execute(
        """UPDATE tasks SET title = ?, due = ?, notes = ?, status = ?, done_at = ?, updated_at = ? WHERE id = ?""",
        (title.strip() if title else row["title"], None if clear_due else (_day(due) if due else row["due"]),
         notes if notes is not None else row["notes"], status,
         (row["done_at"] or ts) if status == "done" else None, ts, row["id"]),
    )
    if done:
        return f"Checked off \"{row['title']}\"."
    return f"Updated \"{title or row['title']}\"."


def listing(conn: sqlite3.Connection, include_done: bool = False) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        f"""SELECT id, title, notes, due, status, source, done_at FROM tasks
            WHERE status = 'open' {"OR (status = 'done' AND done_at >= ?)" if include_done else ''}
            ORDER BY status = 'done', due IS NULL, due, id""",
        ((datetime.now(UTC) - timedelta(days=7)).isoformat(timespec="seconds"),) if include_done else (),
    ).fetchall()
    return [dict(r) for r in rows]


def import_actions(conn: sqlite3.Connection, cfg: Config, now: datetime) -> int:
    """Things to do that Claude picked out of messages join the list; one canceled since comes off it."""
    ensure(conn)
    n = 0
    for h in conn.execute(
        """SELECT * FROM happenings WHERE kind = 'action' AND status = 'active'
           AND id NOT IN (SELECT happening FROM tasks WHERE happening IS NOT NULL)"""
    ).fetchall():
        if not cfg.is_active(h["course_code"]):
            continue
        note = " ".join(x for x in (h["note"], f"From {happenings._from(dict(h))}.", h["link"]) if x)
        if add(conn, h["title"], h["starts_at"], note, source=h["source"], happening=h["id"]) is not None:
            n += 1
            continue
        for t in conn.execute("SELECT id, title FROM tasks WHERE status = 'open' AND happening IS NULL").fetchall():
            if happenings._norm(t["title"]) == happenings._norm(h["title"]):  # he added it himself: remember where it came from
                conn.execute("UPDATE tasks SET happening = ? WHERE id = ?", (h["id"], t["id"]))
                break
    for t in conn.execute(
        """SELECT t.id, t.due, h.status AS h_status, h.starts_at FROM tasks t JOIN happenings h ON h.id = t.happening
           WHERE t.status = 'open'"""
    ).fetchall():
        if t["h_status"] == "canceled":
            conn.execute("UPDATE tasks SET status = 'deleted', updated_at = ? WHERE id = ?", (_ts(), t["id"]))
        elif t["starts_at"] and _day(t["starts_at"]) != t["due"] and t["due"] is not None:
            conn.execute("UPDATE tasks SET due = ?, updated_at = ? WHERE id = ?", (_day(t["starts_at"]), _ts(), t["id"]))
    return n


# ---- Google Tasks ----------------------------------------------------------------------------------------------


def connected() -> bool:
    return bool(secrets.get(TOKEN))


def connect(client_file=None) -> str:
    """The one-time browser sign-in for Google Tasks, then the "Oso" list."""
    from . import gcal

    creds = gcal.sign_in(SCOPES, client_file)
    secrets.set(TOKEN, creds.to_json())
    _list_id(_session())
    return LIST_NAME


def disconnect() -> None:
    secrets.delete(TOKEN)
    secrets.delete(LIST_ID)


def _session():
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    raw = secrets.get(TOKEN)
    if not raw:
        raise NotConnected("Google Tasks is not connected")
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        secrets.set(TOKEN, creds.to_json())
    return AuthorizedSession(creds)


def _list_id(session) -> str:
    """The "Oso" task list, made the first time (or again, if he deleted it)."""
    lid = secrets.get(LIST_ID)
    if lid:
        r = session.get(f"{API}/users/@me/lists/{lid}")
        if r.ok:
            return lid
    r = session.get(f"{API}/users/@me/lists", params={"maxResults": 100})
    r.raise_for_status()
    for item in r.json().get("items", []):
        if item.get("title") == LIST_NAME:
            secrets.set(LIST_ID, item["id"])
            return item["id"]
    r = session.post(f"{API}/users/@me/lists", json={"title": LIST_NAME})
    r.raise_for_status()
    secrets.set(LIST_ID, r.json()["id"])
    return r.json()["id"]


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _body(t: sqlite3.Row) -> dict:
    body = {"title": t["title"], "notes": t["notes"] or "", "status": "completed" if t["status"] == "done" else "needsAction"}
    body["due"] = f"{t['due']}T00:00:00.000Z" if t["due"] else None
    if t["status"] != "done":
        body["completed"] = None
    return body


def sync(conn: sqlite3.Connection, cfg: Config, now: datetime, session=None) -> dict[str, int]:
    """Bring the list in Oso and the "Oso" list in Google Tasks into line."""
    ensure(conn)
    counts = {"from_google": 0, "to_google": 0}
    if session is None:
        if not connected():
            return counts
        session = _session()
    lid = _list_id(session)
    since = conn.execute("SELECT value FROM meta WHERE key = 'tasks_pulled'").fetchone()
    params: dict = {"showCompleted": "true", "showHidden": "true", "showDeleted": "true", "maxResults": 100}
    if since:
        params["updatedMin"] = (_when(since[0]) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    pulled_at = _ts()
    while True:
        r = session.get(f"{API}/lists/{lid}/tasks", params=params)
        r.raise_for_status()
        data = r.json()
        for g in data.get("items", []):
            counts["from_google"] += _take(conn, g)
        if not data.get("nextPageToken"):
            break
        params["pageToken"] = data["nextPageToken"]
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('tasks_pulled', ?)", (pulled_at,))
    for t in conn.execute("SELECT * FROM tasks WHERE pushed_at IS NULL OR updated_at > pushed_at").fetchall():
        if t["status"] == "deleted":
            if t["google_id"]:
                d = session.delete(f"{API}/lists/{lid}/tasks/{t['google_id']}")
                if d.status_code not in (200, 204, 404, 410):
                    d.raise_for_status()
        elif t["google_id"]:
            p = session.patch(f"{API}/lists/{lid}/tasks/{t['google_id']}", json=_body(t))
            if p.status_code in (404, 410):  # gone from Google: put it back
                conn.execute("UPDATE tasks SET google_id = NULL WHERE id = ?", (t["id"],))
                p = session.post(f"{API}/lists/{lid}/tasks", json=_body(t))
                p.raise_for_status()
                conn.execute("UPDATE tasks SET google_id = ? WHERE id = ?", (p.json()["id"], t["id"]))
            else:
                p.raise_for_status()
        else:
            p = session.post(f"{API}/lists/{lid}/tasks", json=_body(t))
            p.raise_for_status()
            conn.execute("UPDATE tasks SET google_id = ? WHERE id = ?", (p.json()["id"], t["id"]))
        conn.execute("UPDATE tasks SET pushed_at = ? WHERE id = ?", (_ts(), t["id"]))
        counts["to_google"] += 1
    return counts


def _take(conn: sqlite3.Connection, g: dict) -> int:
    """One task as Google has it. Returns 1 if it changed the list in Oso."""
    status = "deleted" if g.get("deleted") else "done" if g.get("status") == "completed" else "open"
    due = _day(g["due"]) if g.get("due") else None
    title = (g.get("title") or "").strip()
    updated = _when(g.get("updated")) or datetime.now(UTC)
    row = conn.execute("SELECT * FROM tasks WHERE google_id = ?", (g["id"],)).fetchone()
    ts = _ts()
    if row is None:
        if status == "deleted" or not title:
            return 0
        conn.execute(
            """INSERT INTO tasks (title, notes, due, status, source, google_id, created_at, updated_at, pushed_at, done_at)
               VALUES (?, ?, ?, ?, 'google', ?, ?, ?, ?, ?)""",
            (title, g.get("notes") or None, due, status, g["id"], ts, ts, ts, ts if status == "done" else None),
        )
        return 1
    mine = row["pushed_at"] is None or row["updated_at"] > row["pushed_at"]
    if mine and _when(row["updated_at"]) > updated:
        return 0  # changed in Oso after this: goes out on this check
    same = (row["title"], row["notes"] or "", row["due"], row["status"]) == (title or row["title"], g.get("notes") or "", due, status)
    if same:
        if mine:
            conn.execute("UPDATE tasks SET pushed_at = ? WHERE id = ?", (ts, row["id"]))
        return 0
    conn.execute(
        "UPDATE tasks SET title = ?, notes = ?, due = ?, status = ?, done_at = ?, updated_at = ?, pushed_at = ? WHERE id = ?",
        (title or row["title"], g.get("notes") or None, due, status,
         (row["done_at"] or ts) if status == "done" else None, ts, ts, row["id"]),
    )
    return 1


# ---- the briefing ----------------------------------------------------------------------------------------------


def free_today(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[tuple[datetime, datetime]]:
    """His free stretches for the rest of today, an hour or longer, inside waking hours."""
    from . import rules

    first, last = rules._day_window(cfg)
    start = max(datetime.combine(now.date(), first), rules._quarter(rules._naive(now, cfg)))
    end = datetime.combine(now.date(), last)
    out = []
    for s, e in sorted(rules._busy(conn, cfg, now, now.date())):
        if s > start and s - start >= timedelta(hours=1):
            out.append((start, min(s, end)))
        start = max(start, e)
    if end - start >= timedelta(hours=1):
        out.append((start, end))
    return [(s, e) for s, e in out if e - s >= timedelta(hours=1)]


def _t(d: datetime) -> str:
    return d.strftime("%I:%M %p").lstrip("0").replace(":00", "")


def today_lines(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[str]:
    try:
        ensure(conn)
        open_ = listing(conn)
        done = conn.execute("SELECT title FROM tasks WHERE status = 'done' AND done_at >= ? ORDER BY done_at",
                            ((now - DONE_SHOWN).astimezone(UTC).isoformat(timespec="seconds"),)).fetchall()
    except sqlite3.Error:
        return []
    if not open_ and not done:
        return []
    today, week = now.date(), now.date() + timedelta(days=7)
    lines = ["## Tasks"]
    later = 0
    for t in open_:
        d = date.fromisoformat(t["due"]) if t["due"] else None
        if d and d > week:
            later += 1
            continue
        when = ("overdue, was due " + d.strftime("%a %b %d")) if d and d < today else "today" if d == today else \
            ("by " + d.strftime("%a %b %d")) if d else "whenever"
        lines.append(f"- {t['title']} ({when}){' [from ' + t['source'] + ']' if t['source'] in ('email', 'groupme', 'canvas') else ''}")
    if later:
        lines.append(f"- And {later} more due after this week.")
    if done:
        lines.append(f"- Checked off since yesterday: {', '.join(r['title'] for r in done)}.")
    free = free_today(conn, cfg, now)
    if free and open_:
        lines.append(f"- Free time left today: {', '.join(f'{_t(s)}–{_t(e)}' for s, e in free)}.")
    lines.append("")
    return lines
