"""Picking out what matters in school email and GroupMe messages.

`mail.py` and `groupme.py` keep each new message as a short record. On every check, the ones not set aside as
noise go to Claude in small batches, through Claude Code on the laptop (no API use, the same way handwriting is
read). For each message Claude says whether it matters and, if it does, the facts in it: a deadline, an event,
an action he needs to take, or a change to something already known (moved, canceled), with the course or group
it belongs to.

Deadlines join his deadlines list; one that Canvas or the syllabus already has is merged with it, and a moved one
is recorded as an urgent change, like a moved Canvas due date. Events and actions are kept as happenings
(`happenings.py`); a change updates the happening it changes. Once a message is read, its text is dropped: only
the facts, the sender, the subject, and a link back to the message are kept.

There is no limit by default; `message_reads_per_day` (settings) can cap how many messages Claude reads a day.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta

from . import happenings
from .config import Config
from .db import EFFECTIVE, Item, now_iso

log = logging.getLogger("oso.messages")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,          -- email or groupme
    external_id TEXT NOT NULL,
    sender      TEXT,
    address     TEXT,
    subject     TEXT,
    channel     TEXT,                   -- GroupMe group, or the mailing list
    sent_at     TEXT,
    text        TEXT,                   -- dropped once Claude has read it
    link        TEXT,
    noise       TEXT,                   -- why it was set aside without Claude reading it
    state       TEXT NOT NULL DEFAULT 'new',  -- new, noise, read, failed
    attempts    INTEGER NOT NULL DEFAULT 0,
    facts       INTEGER NOT NULL DEFAULT 0,
    stored_at   TEXT NOT NULL,
    read_at     TEXT,
    UNIQUE (source, external_id)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

EMAIL_BATCH = 8
GROUP_BATCH = 40
CHECK_MINUTES = 4
MAX_ATTEMPTS = 3


class NotConnected(Exception):
    pass


def ensure(conn: sqlite3.Connection) -> None:
    from . import schema

    schema.apply(conn)


def meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    ensure(conn)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def known(conn: sqlite3.Connection, source: str, external_id: str) -> bool:
    return conn.execute("SELECT 1 FROM messages WHERE source = ? AND external_id = ?", (source, external_id)).fetchone() is not None


def store(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO messages (source, external_id, sender, address, subject, channel, sent_at, text, link, noise, state, stored_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rec["source"], rec["external_id"], rec.get("sender"), rec.get("address"), rec.get("subject"), rec.get("channel"),
         rec.get("sent_at"), None if rec.get("noise") else rec.get("text"), rec.get("link"), rec.get("noise"),
         "noise" if rec.get("noise") else "new", now_iso()),
    )


def waiting(conn: sqlite3.Connection) -> int:
    ensure(conn)
    return conn.execute("SELECT COUNT(*) FROM messages WHERE state = 'new'").fetchone()[0]


# ---- reading with Claude --------------------------------------------------------------------------------

PROMPT = """You are reading a college student's new messages ({what}) for Oso, his study assistant. Today is {today} ({tz}).
Pick out only facts that affect his schedule or what he has to do. Most messages don't matter: newsletters,
chatter, jokes, reactions, ads, and general announcements with nothing he must attend or do. Notes about his classes
always matter: a class canceled or moved (time or room), something to bring to class, or something to do before it.

For each message that matters, list its facts. Each fact is one of:
- "deadline": coursework due (an assignment, quiz, exam, reading, form for a class) with a due date
- "event": something at a time and place he might attend (a meeting, practice, review session, social event)
- "action": something he needs to do that is not coursework (register, sign up, pay, reply, pick up), with when it is due or opens

For a fact that changes something already known (listed below), set "about" to its id ("item:12" for a deadline,
"happening:4" for an event or action) and "change" to "moved", "canceled", or "same" (a reminder of it, nothing new).
Otherwise "about" is null and "change" is "new".

Answer with JSON only, no other text, in exactly this shape:
{{"messages": [{{"n": 1, "matters": true, "facts": [{{"type": "event", "title": "Chapter meeting", "when": "2026-10-09T18:00",
"ends": null, "where": "Soccer fields", "course": null, "kind": null, "about": "happening:4", "change": "moved",
"urgent": true, "summary": "The chapter meeting moved to the soccer fields at 6."}}]}}]}}

Rules:
- "when" and "ends" are local times as YYYY-MM-DDTHH:MM, or YYYY-MM-DD when there is no time. Resolve "tomorrow",
  "Friday", and "next week" from the message's date. If there is no date at all, leave the fact out unless it is an action.
- "course" is the code of one of his courses, or null. "kind" (deadlines only) is assignment, quiz, exam, reading, or other.
- "title" is short and plain, as it would appear on a calendar. "summary" is one sentence.
- A class meeting canceled or moved (time or room) that is in his classes below: an "event" with "about" set to
  that meeting's id and "change" "canceled" or "moved" (with the new "when" and "ends", or the new "where").
  Only that one meeting; "class is remote today" is a move with "where" "Online". A class that isn't listed is an
  "event" titled with the course and what happened ("PHYS 101 canceled"), at the class time, with "change" "new".
- Something to bring to a class or do before it is an "action" ("Bring a calculator to PHYS 101") due when that
  class starts, unless it is coursework with a due date, which is a "deadline".
- "urgent" is true for anything moved or canceled within two days, or due within two days.
- Never invent a fact that is not in the message. A message that matters has at least one fact.

His courses: {courses}
Known deadlines (next 30 days): {items}
Known events and actions: {known}
His classes this week: {classes}

The messages follow as JSON."""


def _claude() -> str | None:
    return shutil.which("claude")


def ask_claude(exe: str, cfg: Config, prompt: str, payload: str) -> str:
    """One batch through Claude Code, with the messages on standard input. Raises subprocess.SubprocessError."""
    result = subprocess.run(
        # Messages are written by strangers, so this Claude gets no tools at all: text in, text out.
        [exe, "-p", prompt, "--model", cfg.transcribe_model, "--output-format", "text", "--tools", "", "--strict-mcp-config",
         "--max-turns", "1"],
        input=payload, cwd=str(cfg.vault), capture_output=True, text=True, encoding="utf-8", timeout=300, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise subprocess.SubprocessError((result.stderr or result.stdout or "no output").strip()[:200])
    return result.stdout


def parse_answer(text: str) -> list[dict]:
    """Claude's JSON, tolerating a code fence or a sentence around it."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in the answer")
    data = json.loads(m.group(0))
    return data.get("messages", []) if isinstance(data, dict) else []


def _context(conn: sqlite3.Connection, cfg: Config, now: datetime) -> dict:
    courses = ", ".join(f"{c.code} ({c.name})" for c in cfg.courses if not c.finished) or "none set up"
    soon = (now + timedelta(days=30)).isoformat(timespec="minutes")
    rows = conn.execute(
        f"""SELECT id, kind, {EFFECTIVE} FROM items WHERE deleted_at IS NULL AND merged_into IS NULL AND due_at >= ? AND due_at <= ?
            ORDER BY due_at LIMIT 80""",
        ((now - timedelta(days=1)).isoformat(timespec="minutes"), soon),
    ).fetchall()
    items = "; ".join(f"item:{r['id']} {r['course_code'] or ''} {r['title']} ({r['kind']}) due {r['due_at'][:16]}" for r in rows) or "none"
    from . import classes

    lessons = classes.upcoming(conn, cfg, now, 7)
    in_class = {h["id"] for h in lessons}
    hs = [h for h in happenings.upcoming(conn, cfg, now, 30) if h["id"] not in in_class and h["source"] != "class"]
    known_ = "; ".join(f"happening:{h['id']} {h['kind']} {h['title']} {h['starts_at'] or 'no date'}{' at ' + h['location'] if h['location'] else ''}"
                       for h in hs[:80]) or "none"
    lessons_ = "; ".join(f"happening:{h['id']} {h['course_code']} {h['title']} {h['starts_at']}{' at ' + h['location'] if h['location'] else ''}"
                         for h in lessons) or "not known"
    return {"courses": courses, "items": items, "known": known_, "classes": lessons_}


def _batches(conn: sqlite3.Connection) -> list[tuple[str, list[sqlite3.Row]]]:
    """Email in small batches; GroupMe a batch per group, so each chat is read with its own context."""
    rows = conn.execute("SELECT * FROM messages WHERE state = 'new' ORDER BY sent_at").fetchall()
    out: list[tuple[str, list]] = []
    email = [r for r in rows if r["source"] == "email"]
    for i in range(0, len(email), EMAIL_BATCH):
        out.append(("school email", email[i:i + EMAIL_BATCH]))
    groups: dict[str, list] = {}
    for r in rows:
        if r["source"] == "groupme":
            groups.setdefault(r["channel"] or "a group", []).append(r)
    for name, msgs in groups.items():
        for i in range(0, len(msgs), GROUP_BATCH):
            out.append((f"the GroupMe group \"{name}\"", msgs[i:i + GROUP_BATCH]))
    canvas = [r for r in rows if r["source"] == "canvas"]
    for i in range(0, len(canvas), EMAIL_BATCH):
        out.append(("Canvas announcements and inbox messages from his instructors", canvas[i:i + EMAIL_BATCH]))
    return out


def used_today(conn: sqlite3.Connection, now: datetime) -> int:
    day, _, n = (meta_get(conn, "messages_read") or "").partition(" ")
    return int(n) if day == now.date().isoformat() else 0


def read_new(conn: sqlite3.Connection, cfg: Config, now: datetime, ask=None) -> dict[str, int]:
    """Have Claude read waiting messages, within the daily limit and this check's time. `ask(prompt, payload)` is
    replaced in tests."""
    ensure(conn)
    counts = {"read": 0, "facts": 0, "failed": 0, "waiting": 0}
    if ask is None:
        exe = _claude()
        if not exe:
            counts["waiting"] = waiting(conn)
            return counts
        ask = lambda prompt, payload: ask_claude(exe, cfg, prompt, payload)  # noqa: E731
    limited = cfg.message_reads_per_day > 0
    allowance = max(0, cfg.message_reads_per_day - used_today(conn, now)) if limited else 10**9
    deadline = time.monotonic() + CHECK_MINUTES * 60
    for what, batch in _batches(conn):
        if allowance <= 0 or time.monotonic() >= deadline:
            break
        batch = batch[:allowance]
        ctx = _context(conn, cfg, now)
        prompt = PROMPT.format(what=what, today=now.strftime("%A %Y-%m-%d %H:%M"), tz=cfg.timezone, **ctx)
        payload = json.dumps([
            {"n": i + 1, "from": r["sender"], "subject": r["subject"] or None, "sent": r["sent_at"], "text": r["text"]}
            for i, r in enumerate(batch)
        ], ensure_ascii=False)
        try:
            answers = {int(a.get("n", 0)): a for a in parse_answer(ask(prompt, payload))}
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            log.warning("could not read messages: %s", type(e).__name__)
            for r in batch:
                conn.execute(
                    "UPDATE messages SET attempts = attempts + 1, state = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE state END WHERE id = ?",
                    (MAX_ATTEMPTS, r["id"]),
                )
            counts["failed"] += len(batch)
            conn.commit()
            continue
        for i, r in enumerate(batch):
            a = answers.get(i + 1, {})
            n = 0
            if a.get("matters"):
                for fact in a.get("facts") or []:
                    try:
                        n += apply_fact(conn, cfg, now, dict(r), fact)
                    except (ValueError, TypeError, KeyError) as e:
                        log.warning("skipped a fact: %s", type(e).__name__)
            # Facts, not mail: the text goes once it has been read.
            conn.execute("UPDATE messages SET state = 'read', text = NULL, facts = ?, read_at = ? WHERE id = ?", (n, now_iso(), r["id"]))
            counts["facts"] += n
        counts["read"] += len(batch)
        allowance -= len(batch)
        meta_set(conn, "messages_read", f"{now.date().isoformat()} {used_today(conn, now) + len(batch)}")
        conn.commit()
    counts["waiting"] = waiting(conn)
    return counts


# ---- turning facts into deadlines and happenings ---------------------------------------------------------


def _when(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()[:16]
    datetime.fromisoformat(value)  # raises ValueError on anything that is not a date
    return value


def _course(cfg: Config, code) -> str | None:
    c = cfg.course_for(code) if isinstance(code, str) else None
    return c.code if c else None


def _ref(about) -> tuple[str, int] | None:
    m = re.fullmatch(r"(item|happening):(\d+)", str(about or "").strip())
    return (m.group(1), int(m.group(2))) if m else None


def apply_fact(conn: sqlite3.Connection, cfg: Config, now: datetime, msg: dict, fact: dict) -> int:
    """Keep one fact. Returns 1 if it added or changed something, 0 if it was already known."""
    kind = fact.get("type")
    title = (fact.get("title") or "").strip()[:200]
    if kind not in ("deadline", "event", "action") or not title:
        return 0
    when, ends = _when(fact.get("when")), _when(fact.get("ends"))
    change = fact.get("change") or "new"
    ref = _ref(fact.get("about"))
    summary = (fact.get("summary") or "").strip()[:300] or None
    course = _course(cfg, fact.get("course"))
    if ref and change == "same":
        return 0
    if ref and ref[0] == "item":
        return _change_item(conn, cfg, now, msg, ref[1], change, when, summary)
    if ref and ref[0] == "happening" and change in ("moved", "canceled"):
        ok = happenings.change(conn, ref[1], now, canceled=change == "canceled", starts_at=when, ends_at=ends,
                               location=(fact.get("where") or None), note=summary, link=msg.get("link"))
        return int(ok)
    if kind == "deadline":
        if not when:
            return 0
        return _new_item(conn, cfg, now, msg, title, when, course, fact.get("kind"), summary)
    if kind == "event" and not when:
        return 0
    hid = happenings.add(
        conn, kind, title, when, ends_at=ends, all_day=bool(when and len(when) <= 10), location=fact.get("where") or None,
        course=course, channel=msg.get("channel") or None, source=msg["source"], sender=msg.get("sender"),
        message_id=msg.get("id"), link=msg.get("link"), note=summary, urgent=bool(fact.get("urgent")),
    )
    return int(hid is not None)


def _new_item(conn, cfg: Config, now: datetime, msg: dict, title: str, when: str, course: str | None, kind, summary) -> int:
    from . import merge

    kind = kind if kind in ("assignment", "quiz", "exam", "reading", "other") else "assignment"
    due = when if len(when) > 10 else when + "T23:59"
    due_dt = datetime.fromisoformat(due).replace(tzinfo=cfg.tz)
    external = f"{msg['external_id']}:{merge.normalize_title(title)[:60]}"
    if conn.execute("SELECT 1 FROM items WHERE source = ? AND external_id = ?", (msg["source"], external)).fetchone():
        return 0
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO items (source, external_id, course_code, kind, title, due_at, all_day, url, description, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg["source"], external, course, kind, title, due_dt.isoformat(timespec="minutes"), int(len(when) <= 10), msg.get("link"),
         summary, ts, ts),
    )
    new_id = int(cur.lastrowid)
    merge._link_duplicate(conn, new_id, Item(msg["source"], external, kind, title, due_dt, course_code=course), due_dt.isoformat(timespec="minutes"))
    linked = conn.execute("SELECT merged_into FROM items WHERE id = ?", (new_id,)).fetchone()["merged_into"]
    if linked is None and due_dt - now <= timedelta(days=cfg.urgent_days) and due_dt >= now:
        conn.execute(
            "INSERT INTO changes (item_id, field, old_value, new_value, detected_at, urgency) VALUES (?, 'new', NULL, ?, ?, 'urgent')",
            (new_id, due_dt.isoformat(timespec="minutes"), ts),
        )
    return 1


def _change_item(conn, cfg: Config, now: datetime, msg: dict, item_id: int, change: str, when: str | None, summary) -> int:
    """A message moves or cancels a deadline Oso already has (from Canvas or the syllabus). The message's version
    is kept as its own deadline and shown in place of the old one, and the change is recorded like a moved Canvas
    due date, so the briefing and the calendar hear about it."""
    row = conn.execute(f"SELECT id, kind, url, merged_into, {EFFECTIVE} FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return 0
    ts = now_iso()
    if change == "canceled":
        conn.execute(
            "INSERT INTO changes (item_id, field, old_value, new_value, detected_at, urgency) VALUES (?, 'canceled', ?, ?, ?, 'urgent')",
            (item_id, row["due_at"], summary or "canceled", ts),
        )
        return 1
    if change != "moved" or not when:
        return 0
    due = datetime.fromisoformat(when if len(when) > 10 else when + "T23:59").replace(tzinfo=cfg.tz)
    if row["due_at"] and datetime.fromisoformat(row["due_at"]).astimezone(cfg.tz).replace(second=0) == due:
        return 0  # Canvas already has the new date
    external = f"{msg['external_id']}:moved:{item_id}"
    if conn.execute("SELECT 1 FROM items WHERE source = ? AND external_id = ?", (msg["source"], external)).fetchone():
        return 0
    cur = conn.execute(
        """INSERT INTO items (source, external_id, course_code, kind, title, due_at, all_day, url, description, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg["source"], external, row["course_code"], row["kind"], row["title"], due.isoformat(timespec="minutes"), 0,
         row["url"] or msg.get("link"), summary, ts, ts),
    )
    conn.execute("UPDATE items SET merged_into = ? WHERE id = ?", (int(cur.lastrowid), item_id))
    from .merge import _urgency

    conn.execute(
        "INSERT INTO changes (item_id, field, old_value, new_value, detected_at, urgency) VALUES (?, 'due_at', ?, ?, ?, ?)",
        (int(cur.lastrowid), row["due_at"], due.isoformat(timespec="minutes"), ts, _urgency("due_at", row["kind"], due, now, timedelta(days=cfg.urgent_days))),
    )
    return 1
