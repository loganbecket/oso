"""Class times: when each course meets, put on the Oso calendar and kept current.

Canvas doesn't know when classes meet, so course setup reads the times from the syllabus (or asks) and saves them
here: the days and hours of each meeting (lecture, lab, discussion), where, the first and last day of classes, and
days with no class (holidays, breaks). Every check keeps the next three weeks of meetings as happenings, which go
on the Oso calendar like any other event. A class canceled or moved in an email, a GroupMe message, or a Canvas
announcement changes that one meeting, so the calendar matches what's actually happening; the rest stay put.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta

from . import happenings
from .config import Config

DAYS = "MTWRFSU"  # Monday through Sunday, the way registrars write them (R is Thursday, U Sunday)
AHEAD = timedelta(days=21)  # how far ahead meetings are kept on the calendar; extended on every check

SCHEMA = """
CREATE TABLE IF NOT EXISTS class_meetings (
    id         INTEGER PRIMARY KEY,
    course     TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'class',  -- class, lab, discussion, or the syllabus's own word
    days       TEXT NOT NULL,                  -- letters from MTWRFSU
    starts     TEXT NOT NULL,                  -- HH:MM
    ends       TEXT NOT NULL,
    location   TEXT
);
CREATE TABLE IF NOT EXISTS class_terms (
    course     TEXT PRIMARY KEY,
    first_day  TEXT NOT NULL,
    last_day   TEXT NOT NULL,
    no_class   TEXT NOT NULL DEFAULT ''        -- comma-separated YYYY-MM-DD
);
CREATE TABLE IF NOT EXISTS class_occurrences (
    happening  INTEGER PRIMARY KEY,
    course     TEXT NOT NULL,
    slot       TEXT NOT NULL,                  -- YYYY-MM-DDTHH:MM as scheduled, kept when the meeting is moved or canceled
    UNIQUE (course, slot)
);
"""


def ensure(conn: sqlite3.Connection) -> None:
    from . import schema

    schema.apply(conn)


_DAY_WORDS = [  # longest first, so "THURS" wins over "TH" and "T"
    ("THURSDAY", "R"), ("TUESDAY", "T"), ("WEDNESDAY", "W"), ("SATURDAY", "S"), ("MONDAY", "M"), ("FRIDAY", "F"), ("SUNDAY", "U"),
    ("THURS", "R"), ("TUES", "T"), ("THUR", "R"), ("THU", "R"), ("TUE", "T"), ("WED", "W"), ("MON", "M"), ("FRI", "F"),
    ("SAT", "S"), ("SUN", "U"), ("TH", "R"), ("TU", "T"), ("SA", "S"), ("SU", "U"),
    ("M", "M"), ("T", "T"), ("W", "W"), ("R", "R"), ("F", "F"), ("S", "S"), ("U", "U"),
]
_DAY_RE = re.compile("|".join(w for w, _ in _DAY_WORDS))


def _days(text: str) -> str:
    """'MWF', 'TR', 'Tu/Th', 'Mon Wed Fri' and the like, as letters from MTWRFSU."""
    t = re.sub(r"[\s,/&+.-]|AND", "", (text or "").upper())
    found, pos = set(), 0
    while pos < len(t):
        m = _DAY_RE.match(t, pos)
        if not m:
            raise ValueError(f"Couldn't tell which days {text!r} means; use letters like MWF or TR.")
        found.add(dict(_DAY_WORDS)[m.group(0)])
        pos = m.end()
    if not found:
        raise ValueError(f"Couldn't tell which days {text!r} means; use letters like MWF or TR.")
    return "".join(c for c in DAYS if c in found)


def _hhmm(text: str) -> str:
    """'9:30', '9:30 AM', '2 p.m.', '14:00' as HH:MM."""
    t = text.strip().upper().replace(".", "").replace(" ", "")
    for fmt in ("%H:%M", "%I:%M%p", "%I%p", "%H"):
        try:
            return datetime.strptime(t, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError(f"Couldn't read the time {text!r}.")


def set_times(conn: sqlite3.Connection, cfg: Config, course: str, meetings: list[dict], first_day: str, last_day: str,
              no_class: list[str] | None = None, now: datetime | None = None) -> dict:
    """Save when a course meets (replacing what was saved before) and bring the calendar in line."""
    ensure(conn)
    c = cfg.course_for(course)
    if c is None:
        raise ValueError(f"There's no course {course!r} set up in Oso.")
    if not meetings:
        raise ValueError("A course needs at least one meeting time.")
    first, last = date.fromisoformat(first_day[:10]), date.fromisoformat(last_day[:10])
    if last < first:
        raise ValueError("The last day of classes is before the first.")
    rows = []
    for m in meetings:
        starts, ends = _hhmm(str(m["starts"])), _hhmm(str(m["ends"]))
        if ends <= starts:
            raise ValueError(f"A meeting ends ({ends}) before it starts ({starts}).")
        rows.append((c.code, (m.get("kind") or "class").strip().lower(), _days(str(m["days"])), starts, ends, m.get("location") or None))
    skip = sorted({date.fromisoformat(d[:10]).isoformat() for d in no_class or []})
    old = {r["id"] for r in conn.execute("SELECT id FROM class_meetings WHERE course = ?", (c.code,))}
    conn.execute("DELETE FROM class_meetings WHERE course = ?", (c.code,))
    conn.executemany("INSERT INTO class_meetings (course, kind, days, starts, ends, location) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.execute("INSERT OR REPLACE INTO class_terms (course, first_day, last_day, no_class) VALUES (?, ?, ?, ?)",
                 (c.code, first.isoformat(), last.isoformat(), ",".join(skip)))
    now = now or datetime.now(cfg.tz)
    removed = _drop_future(conn, c.code, now) if old else 0
    added = extend(conn, cfg, now)
    return {"course": c.code, "meetings": len(rows), "on_calendar": added, "removed": removed}


def times(conn: sqlite3.Connection, course: str) -> dict | None:
    ensure(conn)
    term = conn.execute("SELECT * FROM class_terms WHERE course = ?", (course,)).fetchone()
    if term is None:
        return None
    ms = conn.execute("SELECT kind, days, starts, ends, location FROM class_meetings WHERE course = ? ORDER BY id", (course,)).fetchall()
    return {"meetings": [dict(m) for m in ms], "first_day": term["first_day"], "last_day": term["last_day"],
            "no_class": [d for d in term["no_class"].split(",") if d]}


def missing(conn: sqlite3.Connection, cfg: Config) -> list[str]:
    """Current courses whose class times Oso doesn't know."""
    ensure(conn)
    known = {r[0] for r in conn.execute("SELECT course FROM class_terms")}
    return [c.name for c in cfg.courses if not c.finished and c.code not in known]


def _title(cfg: Config, course: str, kind: str) -> str:
    c = cfg.course_for(course)
    name = c.name if c else course
    return name if kind == "class" else f"{name} {kind}"


def _drop_future(conn: sqlite3.Connection, course: str, now: datetime) -> int:
    """The class times changed: take the meetings still to come off the calendar, so the new times can go on. One
    already canceled or moved by a message stays as it is."""
    n = 0
    for r in conn.execute(
        """SELECT o.happening FROM class_occurrences o JOIN happenings h ON h.id = o.happening
           WHERE o.course = ? AND o.slot >= ? AND h.status = 'active' AND h.change_note IS NULL""",
        (course, now.date().isoformat()),
    ).fetchall():
        happenings.change(conn, r["happening"], now, canceled=True, note="Class times changed.")
        conn.execute("DELETE FROM class_occurrences WHERE happening = ?", (r["happening"],))
        conn.execute("UPDATE happenings SET urgent = 0 WHERE id = ?", (r["happening"],))  # not news: he set the new times
        n += 1
    return n


def extend(conn: sqlite3.Connection, cfg: Config, now: datetime) -> int:
    """Keep the next three weeks of meetings for every current course. A meeting already kept (even one canceled or
    moved since) is never added again. Returns how many were added."""
    ensure(conn)
    added = 0
    horizon = now.date() + AHEAD
    for term in conn.execute("SELECT * FROM class_terms").fetchall():
        course = term["course"]
        c = cfg.course_for(course)
        if c is None or c.finished:
            continue
        skip = set(d for d in term["no_class"].split(",") if d)
        start = max(now.date(), date.fromisoformat(term["first_day"]))
        end = min(horizon, date.fromisoformat(term["last_day"]))
        meetings = conn.execute("SELECT * FROM class_meetings WHERE course = ?", (course,)).fetchall()
        d = start
        while d <= end:
            if d.isoformat() not in skip:
                for m in meetings:
                    if DAYS[d.weekday()] not in m["days"]:
                        continue
                    slot = f"{d.isoformat()}T{m['starts']}"
                    if conn.execute("SELECT 1 FROM class_occurrences WHERE course = ? AND slot = ?", (course, slot)).fetchone():
                        continue
                    hid = happenings.add(conn, "event", _title(cfg, course, m["kind"]), slot, ends_at=f"{d.isoformat()}T{m['ends']}",
                                         location=m["location"], course=course, source="class", note="Class, from the syllabus.")
                    if hid is None:  # the same thing is already kept for that day (added by hand, say)
                        continue
                    conn.execute("INSERT INTO class_occurrences (happening, course, slot) VALUES (?, ?, ?)", (hid, course, slot))
                    added += 1
            d += timedelta(days=1)
    return added


def upcoming(conn: sqlite3.Connection, cfg: Config, now: datetime, days: int = 7) -> list[dict]:
    """His class meetings for the next `days` days, for the message reader to match cancellations against."""
    ensure(conn)
    end = (now.date() + timedelta(days=days)).isoformat() + "T23:59"
    rows = conn.execute(
        """SELECT h.* FROM happenings h JOIN class_occurrences o ON o.happening = h.id
           WHERE h.status = 'active' AND h.starts_at >= ? AND h.starts_at <= ? ORDER BY h.starts_at""",
        (now.date().isoformat(), end),
    ).fetchall()
    return [dict(r) for r in rows]


def is_class(conn: sqlite3.Connection, happening: int) -> bool:
    ensure(conn)
    return conn.execute("SELECT 1 FROM class_occurrences WHERE happening = ?", (happening,)).fetchone() is not None


def today_lines(conn: sqlite3.Connection, cfg: Config) -> list[str]:
    try:
        names = missing(conn, cfg)
    except sqlite3.Error:
        return []
    if not names:
        return []
    return ["## Class times", f"- Oso doesn't know when {', '.join(names)} {'meets' if len(names) == 1 else 'meet'}, so "
            f"{'it is' if len(names) == 1 else 'they are'} not on the calendar. Ask Claude to add the class times.", ""]
