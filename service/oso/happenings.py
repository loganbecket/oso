"""Happenings: what competes for the student's time besides coursework, kept alongside his deadlines.

A happening is an event (what, when, where) or an action he needs to take (register, sign, reply), picked out
of his school email and GroupMe by Claude (`messages.py`) or added by Claude when he asks. Deadlines picked out
of messages are not happenings: they join his deadlines list (`items`).

Events go on the Oso calendar, marked as Oso's, and a change moves or cancels the event Oso added. On every
check Oso reads the whole Oso calendar back, including events he or Claude added, so the briefing knows
everything on his schedule (`Today's schedule`, `Coming up`, and the conflicts in `Heads up`).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, time, timedelta

from .config import Config
from .db import EFFECTIVE, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS happenings (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,              -- event or action
    title       TEXT NOT NULL,
    starts_at   TEXT,                       -- local ISO time; for an action, when it is due or opens
    ends_at     TEXT,
    all_day     INTEGER NOT NULL DEFAULT 0,
    location    TEXT,
    course_code TEXT,
    channel     TEXT,                       -- the GroupMe group or mailing list it came from
    source      TEXT NOT NULL,              -- email, groupme, or chat (added by Claude when asked)
    sender      TEXT,
    message_id  INTEGER,
    link        TEXT,
    note        TEXT,
    status      TEXT NOT NULL DEFAULT 'active',  -- active or canceled
    change_note TEXT,                       -- the latest change, in a sentence
    changed_at  TEXT,
    urgent      INTEGER NOT NULL DEFAULT 0,
    event_id    TEXT,                       -- the Oso calendar event Oso made for it
    synced_at   TEXT,
    first_seen  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_view (
    event_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    starts_at   TEXT NOT NULL,
    ends_at     TEXT,
    all_day     INTEGER NOT NULL DEFAULT 0,
    location    TEXT,
    tag         TEXT,                       -- happening:<id> or alert for events Oso made; empty for his own
    read_at     TEXT NOT NULL
);
"""

URGENT_WINDOW = timedelta(days=2)  # a change this close is flagged, like a moved Canvas due date


def ensure(conn: sqlite3.Connection) -> None:
    from . import schema

    schema.apply(conn)


def norm(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", title.lower())).strip()


def add(conn: sqlite3.Connection, kind: str, title: str, starts_at: str | None, *, ends_at: str | None = None,
        all_day: bool = False, location: str | None = None, course: str | None = None, channel: str | None = None,
        source: str = "chat", sender: str | None = None, message_id: int | None = None, link: str | None = None,
        note: str | None = None, urgent: bool = False, remind: bool = False) -> int | None:
    """Keep a new happening. Returns its id, or None when the same thing (same title, same day) is already kept.
    remind: a pop-up on his phone when it starts ("remind me when class lets out")."""
    ensure(conn)
    day = (starts_at or "")[:10]
    for r in conn.execute("SELECT id, title FROM happenings WHERE status = 'active' AND kind = ? AND substr(COALESCE(starts_at, ''), 1, 10) = ?", (kind, day)):
        if norm(r["title"]) == norm(title):
            return None
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO happenings (kind, title, starts_at, ends_at, all_day, location, course_code, channel, source, sender,
                                   message_id, link, note, urgent, remind, first_seen, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (kind, title, starts_at, ends_at, int(all_day), location, course, channel, source, sender, message_id, link, note,
         int(urgent), int(remind), ts, ts),
    )
    return int(cur.lastrowid)


def change(conn: sqlite3.Connection, hid: int, now: datetime, *, canceled: bool = False, starts_at: str | None = None,
           ends_at: str | None = None, location: str | None = None, title: str | None = None, note: str | None = None,
           link: str | None = None) -> bool:
    """Move, rename, relocate, or cancel a happening. A change within two days is flagged urgent."""
    ensure(conn)
    row = conn.execute("SELECT * FROM happenings WHERE id = ?", (hid,)).fetchone()
    if row is None:
        return False
    when = starts_at or row["starts_at"]
    soon = False
    if when:
        try:
            soon = _local(when, now) - now <= URGENT_WINDOW
        except ValueError:
            soon = False
    conn.execute(
        """UPDATE happenings SET status = ?, starts_at = ?, ends_at = ?, location = ?, title = ?, change_note = ?, changed_at = ?,
                                 urgent = MAX(urgent, ?), link = COALESCE(?, link), updated_at = ?,
                                 synced_at = NULL WHERE id = ?""",
        ("canceled" if canceled else row["status"], starts_at or row["starts_at"],
         ends_at if starts_at else (ends_at or row["ends_at"]), location or row["location"], title or row["title"],
         note or ("Canceled." if canceled else "Changed."), now.isoformat(timespec="minutes"), int(soon), link, now_iso(), hid),
    )
    return True


def _local(value: str, now: datetime) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=now.tzinfo)
    return dt.astimezone(now.tzinfo) if now.tzinfo else dt  # his time zone, so dates are right near midnight


def upcoming(conn: sqlite3.Connection, cfg: Config, now: datetime, days: int = 14, include_canceled: bool = False) -> list[dict]:
    """Happenings from today on, soonest first."""
    ensure(conn)
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=days)).isoformat() + "T23:59"
    rows = conn.execute(
        f"""SELECT * FROM happenings WHERE {'1' if include_canceled else "status = 'active'"}
            AND (starts_at IS NULL OR (starts_at >= ? AND starts_at <= ?)) ORDER BY starts_at IS NULL, starts_at""",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows if cfg.is_active(r["course_code"])]


# ---- the Oso calendar ---------------------------------------------------------------------------------


def event_body(h: dict, cfg: Config) -> dict:
    lines = [h.get("note") or ""]
    if h.get("channel") or h.get("sender"):
        lines.append(f"From {'GroupMe, ' + h['channel'] if h['source'] == 'groupme' else 'email from ' + (h.get('sender') or 'school')}.")
    elif h["source"] == "chat":
        lines.append("Added by Claude.")
    if h.get("link"):
        lines.append(h["link"])
    lines.append("Added by Oso.")
    body = {
        "summary": h["title"],
        "description": "\n".join(x for x in lines if x),
        "extendedProperties": {"private": {"oso": f"happening:{h['id']}"}},
    }
    if h.get("location"):
        body["location"] = h["location"]
    if h.get("remind"):
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]}
    start = h["starts_at"]
    if h.get("all_day") or len(start) <= 10:
        d = date.fromisoformat(start[:10])
        end = date.fromisoformat(h["ends_at"][:10]) if h.get("ends_at") else d
        body["start"] = {"date": d.isoformat()}
        body["end"] = {"date": (max(end, d) + timedelta(days=1)).isoformat()}
    else:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(h["ends_at"]) if h.get("ends_at") and len(h["ends_at"]) > 10 else s + timedelta(hours=1)
        body["start"] = {"dateTime": s.replace(tzinfo=None).isoformat(timespec="minutes") + ":00", "timeZone": cfg.timezone}
        body["end"] = {"dateTime": max(e, s).replace(tzinfo=None).isoformat(timespec="minutes") + ":00", "timeZone": cfg.timezone}
    return body


def sync_calendar(conn: sqlite3.Connection, cfg: Config, now: datetime, session, cal_id: str) -> dict[str, int]:
    """Put new events on the Oso calendar, move or remove the ones that changed, then read the calendar back."""
    from .gcal import API

    ensure(conn)
    counts = {"added": 0, "moved": 0, "removed": 0, "read": 0}
    recent = (now - timedelta(days=1)).date().isoformat()
    rows = conn.execute(
        """SELECT * FROM happenings WHERE kind = 'event' AND starts_at IS NOT NULL AND starts_at >= ?
           AND ((event_id IS NULL AND status = 'active') OR synced_at IS NULL)""",
        (recent,),
    ).fetchall()
    for r in rows:
        h = dict(r)
        if h["status"] == "canceled":
            if h["event_id"]:
                resp = session.delete(f"{API}/calendars/{cal_id}/events/{h['event_id']}")
                if resp.status_code not in (200, 204, 404, 410):
                    resp.raise_for_status()
                counts["removed"] += 1
            conn.execute("UPDATE happenings SET event_id = NULL, synced_at = ? WHERE id = ?", (now_iso(), h["id"]))
            continue
        if h["event_id"]:
            resp = session.patch(f"{API}/calendars/{cal_id}/events/{h['event_id']}", json=event_body(h, cfg))
            if resp.status_code in (404, 410):  # he deleted it from the calendar himself: leave it deleted
                conn.execute("UPDATE happenings SET synced_at = ? WHERE id = ?", (now_iso(), h["id"]))
                continue
            resp.raise_for_status()
            counts["moved"] += 1
        else:
            resp = session.post(f"{API}/calendars/{cal_id}/events", json=event_body(h, cfg))
            resp.raise_for_status()
            conn.execute("UPDATE happenings SET event_id = ? WHERE id = ?", (resp.json().get("id"), h["id"]))
            counts["added"] += 1
        conn.execute("UPDATE happenings SET synced_at = ? WHERE id = ?", (now_iso(), h["id"]))
    counts["read"] = read_calendar(conn, cfg, now, session, cal_id)
    return counts


def read_calendar(conn: sqlite3.Connection, cfg: Config, now: datetime, session, cal_id: str, days: int = 14) -> int:
    """Keep a copy of the next two weeks of the Oso calendar, everything on it, for the schedule and conflicts."""
    from .gcal import API

    ensure(conn)
    start = datetime.combine(now.date(), time(0), tzinfo=now.tzinfo)
    params = {"timeMin": start.isoformat(), "timeMax": (start + timedelta(days=days + 1)).isoformat(),
              "singleEvents": "true", "orderBy": "startTime", "maxResults": 250}
    resp = session.get(f"{API}/calendars/{cal_id}/events", params=params)
    resp.raise_for_status()
    conn.execute("DELETE FROM calendar_view")
    n = 0
    for e in resp.json().get("items", []):
        if e.get("status") == "cancelled":
            continue
        s, en = e.get("start", {}), e.get("end", {})
        all_day = "date" in s
        starts = s.get("date") or _to_local(s.get("dateTime"), cfg)
        ends = en.get("date") or _to_local(en.get("dateTime"), cfg)
        if all_day and ends:  # Google's end date is the day after
            ends = (date.fromisoformat(ends) - timedelta(days=1)).isoformat()
        tag = (e.get("extendedProperties", {}).get("private", {}) or {}).get("oso", "")
        if not tag and (e.get("summary") or "").startswith("Oso: "):
            tag = "alert"
        conn.execute(
            "INSERT OR REPLACE INTO calendar_view (event_id, title, starts_at, ends_at, all_day, location, tag, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (e["id"], e.get("summary") or "(no title)", starts, ends, int(all_day), e.get("location"), tag, now_iso()),
        )
        n += 1
    return n


def _to_local(value: str | None, cfg: Config) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(cfg.tz).replace(tzinfo=None).isoformat(timespec="minutes")


# ---- the schedule, for Today.md and the briefing --------------------------------------------------------


def schedule(conn: sqlite3.Connection, cfg: Config, now: datetime, days: int = 7) -> list[dict]:
    """Everything on his schedule from today for `days` days, in time order: the Oso calendar as last read (his own
    events, Claude's, and Oso's), plus events Oso knows of that are not on the calendar (not connected, or not yet
    put there). Oso's deadline alerts are left out; deadlines have their own sections."""
    ensure(conn)
    first, last = now.date(), now.date() + timedelta(days=days)
    out, on_calendar = [], set()
    for r in conn.execute("SELECT * FROM calendar_view ORDER BY starts_at"):
        if r["tag"] == "alert":
            continue
        d = date.fromisoformat(r["starts_at"][:10])
        if first <= d <= last:
            if r["tag"].startswith("happening:"):
                on_calendar.add(int(r["tag"].split(":")[1]))
            out.append({"title": r["title"], "starts_at": r["starts_at"], "ends_at": r["ends_at"], "all_day": bool(r["all_day"]),
                        "location": r["location"], "from": _from_tag(conn, r["tag"]), "happening": _hid(r["tag"]),
                        "event_id": r["event_id"]})
    for h in upcoming(conn, cfg, now, days):
        if h["kind"] == "event" and h["starts_at"] and h["id"] not in on_calendar and not (h["event_id"] and _calendar_read(conn)):
            out.append({"title": h["title"], "starts_at": h["starts_at"], "ends_at": h["ends_at"], "all_day": bool(h["all_day"]) or len(h["starts_at"]) <= 10,
                        "location": h["location"], "from": came_from(h), "happening": h["id"], "event_id": h["event_id"]})
    out.sort(key=lambda e: (e["starts_at"][:10], 0 if e["all_day"] else 1, e["starts_at"]))
    return out


def _calendar_read(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM calendar_view LIMIT 1").fetchone() is not None


def _hid(tag: str) -> int | None:
    return int(tag.split(":")[1]) if tag.startswith("happening:") and tag.split(":")[1].isdigit() else None


def _from_tag(conn: sqlite3.Connection, tag: str) -> str:
    hid = _hid(tag)
    if hid is None:
        return "your calendar"
    row = conn.execute("SELECT * FROM happenings WHERE id = ?", (hid,)).fetchone()
    return came_from(dict(row)) if row else "Oso"


def came_from(h: dict) -> str:
    if h["source"] == "groupme":
        return f"GroupMe, {h.get('channel') or 'a group'}"
    if h["source"] == "email":
        return f"email from {h.get('sender') or 'school'}"
    if h["source"] == "rule":
        return "your rule"
    if h["source"] == "class":
        return "class schedule"
    if h["source"] == "canvas":
        return f"Canvas, {h.get('sender') or 'an announcement'}"
    return "added in chat"


def _when(starts: str, ends: str | None = None, all_day: bool = False, with_day: bool = True) -> str:
    d = date.fromisoformat(starts[:10])
    day = d.strftime("%a %b %d") if with_day else ""
    if all_day or len(starts) <= 10:
        return day or "all day"
    t = datetime.fromisoformat(starts).strftime("%I:%M %p").lstrip("0")
    if ends and len(ends) > 10:
        t += "–" + datetime.fromisoformat(ends).strftime("%I:%M %p").lstrip("0")
    return f"{day}, {t}" if day else t


def _exams(conn: sqlite3.Connection, cfg: Config, now: datetime, days: int) -> list[dict]:
    rows = conn.execute(
        f"""SELECT id, kind, {EFFECTIVE} FROM items WHERE deleted_at IS NULL AND merged_into IS NULL"""
    ).fetchall()
    out = []
    for r in rows:
        if r["kind"] != "exam" or not r["due_at"] or not cfg.is_active(r["course_code"]) or r["status"] == "done":
            continue
        due = _local(r["due_at"], now)
        if now.date() <= due.date() <= now.date() + timedelta(days=days):
            course = cfg.course_for(r["course_code"])
            out.append({"title": r["title"], "course": course.name if course else (r["course_code"] or ""), "due": due})
    return out


def conflicts(conn: sqlite3.Connection, cfg: Config, now: datetime, days: int = 7) -> list[str]:
    """Plain sentences: an evening event before an exam, two things at once, and recent changes. Things to do are
    tasks (`tasks.py`)."""
    lines = []
    events = [e for e in schedule(conn, cfg, now, days) if not e["all_day"]]
    for x in _exams(conn, cfg, now, days + 1):
        eve = x["due"].date() - timedelta(days=1)
        for e in events:
            s = datetime.fromisoformat(e["starts_at"])
            if s.date() == eve and s.hour >= 17:
                lines.append(f"{e['title']} ({_when(e['starts_at'], e['ends_at'])}) is the evening before {x['course'] + ' ' if x['course'] else ''}{x['title']} ({x['due'].strftime('%a %b %d')}).")
    for i, a in enumerate(events):
        a_end = datetime.fromisoformat(a["ends_at"]) if a["ends_at"] and len(a["ends_at"]) > 10 else datetime.fromisoformat(a["starts_at"]) + timedelta(hours=1)
        for b in events[i + 1:]:
            b_start = datetime.fromisoformat(b["starts_at"])
            if b_start < a_end and b_start.date() == datetime.fromisoformat(a["starts_at"]).date():
                lines.append(f"{a['title']} and {b['title']} overlap on {_when(b['starts_at'])}.")
    since = (now - timedelta(hours=24)).isoformat(timespec="minutes")
    for r in conn.execute("SELECT * FROM happenings WHERE urgent = 1 AND changed_at >= ? ORDER BY changed_at", (since,)):
        h = dict(r)
        what = "Canceled" if h["status"] == "canceled" else "Changed"
        lines.append(f"{what}: {h['title']}{', now ' + _when(h['starts_at'], h['ends_at'], bool(h['all_day'])) if h['status'] != 'canceled' and h['starts_at'] else ''}"
                     f"{' at ' + h['location'] if h['status'] != 'canceled' and h['location'] else ''}. {h['change_note'] or ''} ({came_from(h)})".rstrip())
    return lines


def today_sections(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[str]:
    ensure(conn)
    lines: list[str] = []
    todays = [e for e in schedule(conn, cfg, now, 0)]
    if todays:
        lines.append("## Today's schedule")
        for e in todays:
            where = f" at {e['location']}" if e["location"] else ""
            lines.append(f"- {_when(e['starts_at'], e['ends_at'], e['all_day'], with_day=False)}: {e['title']}{where} ({e['from']})")
        lines.append("")
    heads = conflicts(conn, cfg, now)
    if heads:
        lines.append("## Heads up")
        lines += [f"- {x}" for x in heads]
        lines.append("")
    later = [e for e in schedule(conn, cfg, now, 7) if e["starts_at"][:10] > now.date().isoformat()]
    if later:
        lines.append("## Coming up")
        for e in later:
            where = f" at {e['location']}" if e["location"] else ""
            lines.append(f"- {_when(e['starts_at'], e['ends_at'], e['all_day'])}: {e['title']}{where} ({e['from']})")
        lines.append("")
    return lines


# ---- changes Claude makes when he asks ----------------------------------------------------------------------


def push(conn: sqlite3.Connection, cfg: Config, now: datetime) -> str | None:
    """Put pending changes on the Oso calendar right away. None when done; a plain sentence when it can't."""
    from . import gcal

    if not gcal.connected():
        return "The Oso calendar isn't connected, so this is kept in Oso's schedule only."
    try:
        session = gcal._session()
        sync_calendar(conn, cfg, now, session, gcal.ensure_calendar(session, cfg))
    except Exception as e:  # noqa: BLE001
        from .sync import plain_error

        return f"Saved, but the Oso calendar couldn't be updated just now ({plain_error(e)}); the next check tries again."
    return None


def change_calendar_event(conn: sqlite3.Connection, cfg: Config, now: datetime, event_id: str, *, cancel: bool = False,
                          start: str | None = None, end: str | None = None, title: str | None = None,
                          location: str | None = None) -> str:
    """Move, rename, or remove an event on the Oso calendar that Oso didn't make (only when he asks)."""
    from . import gcal

    session = gcal._session()
    cal_id = gcal.ensure_calendar(session, cfg)
    url = f"{gcal.API}/calendars/{cal_id}/events/{event_id}"
    if cancel:
        r = session.delete(url)
        if r.status_code not in (200, 204, 404, 410):
            r.raise_for_status()
        read_calendar(conn, cfg, now, session, cal_id)
        return "Removed it from the Oso calendar."
    body: dict = {}
    if title:
        body["summary"] = title
    if location:
        body["location"] = location
    if start:
        h = {"id": 0, "title": title or "", "starts_at": start, "ends_at": end, "all_day": len(start) <= 10, "source": "chat"}
        timed = event_body(h, cfg)
        body["start"], body["end"] = timed["start"], timed["end"]
    r = session.patch(url, json=body)
    r.raise_for_status()
    read_calendar(conn, cfg, now, session, cal_id)
    return "Changed it on the Oso calendar."
