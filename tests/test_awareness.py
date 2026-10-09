"""School email, GroupMe, and the whole week: fetching only what's new, setting noise aside, picking out facts,
keeping them as deadlines and happenings, the Oso calendar, and the schedule in Today.md."""

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import config as cfgmod, db, groupme, happenings, mail, messages, secrets, today
from oso.config import Config, Course

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 7, 7, 0, tzinfo=TZ)


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    store: dict[str, str] = {"groupme_user_id": "me"}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    cfg.vault.mkdir()
    cfgmod.save(cfg)
    with db.connect() as conn:
        messages.ensure(conn)
        yield cfg, conn


# ---- recorded Gmail ------------------------------------------------------------------------------------


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_message(mid: str, sender: str, subject: str, body: str, labels=(), when=NOW, html=False) -> dict:
    return {
        "id": mid,
        "labelIds": ["INBOX", *labels],
        "internalDate": str(int(when.timestamp() * 1000)),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject},
                        {"name": "Date", "value": when.strftime("%a, %d %b %Y %H:%M:%S %z")}],
            "parts": [{"mimeType": "text/html" if html else "text/plain", "body": {"data": _b64(body)}}],
        },
    }


class Resp:
    def __init__(self, body=None, status=200):
        self._body, self.status_code, self.ok = body or {}, status, status < 400

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeGmail:
    def __init__(self, msgs):
        self.msgs = {m["id"]: m for m in msgs}
        self.gets: list[str] = []
        self.queries: list[str] = []

    def get(self, url, params=None):
        if url.endswith("/messages"):
            self.queries.append(params["q"])
            return Resp({"messages": [{"id": i} for i in self.msgs]})
        mid = url.rsplit("/", 1)[1]
        self.gets.append(mid)
        return Resp(self.msgs[mid])


def test_email_fetches_only_new_and_sets_noise_aside(env):
    cfg, conn = env
    cfg.muted_senders = ["@clubs.example.edu"]
    gm = FakeGmail([
        gmail_message("a", "Dr. Lee <lee@school.edu>", "Lab moved", "The lab report is now due Friday.\n\nOn Mon, someone wrote:\n> old"),
        gmail_message("b", "Store <deals@store.com>", "50% off", "Sale!", labels=["CATEGORY_PROMOTIONS"]),
        gmail_message("c", "Canvas <notifications@instructure.com>", "New announcement", "..."),
        gmail_message("d", "Chess <news@clubs.example.edu>", "Newsletter", "..."),
        gmail_message("e", "Registrar <reg@school.edu>", "Registration", "<p>Spring registration opens <b>Monday</b>.</p>", html=True),
    ])
    counts = mail.fetch(conn, cfg, NOW, session=gm)
    assert counts == {"kept": 2, "set_aside": 3}
    rows = {r["external_id"]: r for r in conn.execute("SELECT * FROM messages")}
    assert rows["a"]["state"] == "new" and "due Friday" in rows["a"]["text"] and "old" not in rows["a"]["text"]
    assert rows["e"]["text"].startswith("Spring registration opens") and "<b>" not in rows["e"]["text"]
    assert {rows[x]["noise"] for x in "bcd"} == {"promotion", "Canvas notification", "muted sender"}
    assert rows["b"]["text"] is None  # noise is never kept
    # The next check asks only for what's newer and never fetches a message twice.
    mail.fetch(conn, cfg, NOW, session=gm)
    assert len(gm.gets) == 5 and gm.queries[-1].startswith(f"after:{int(NOW.timestamp())}")


def test_forwarded_school_email_is_unwrapped(env):
    cfg, conn = env
    outlook = ("\n________________________________\nFrom: Lee, Dana <dlee@school.edu>\nSent: Tuesday, October 6, 2026 4:12 PM\n"
               "To: Student, Sam <sam@school.edu>\nSubject: Lab 3 moved\n\nThe lab report is now due Friday.\n")
    canvas = ("---------- Forwarded message ---------\nFrom: Canvas <notifications@instructure.com>\nDate: Tue, Oct 6, 2026\n"
              "Subject: New announcement\nTo: <sam@school.edu>\n\nSomething posted.\n")
    plain = "Hi Sam,\n\nSee you at office hours.\n\nOn Mon, Dana wrote:\nFrom: earlier\n"
    gmail = FakeGmail([gmail_message("f1", "Sam Student <sam@school.edu>", "FW: Lab 3 moved", outlook),
                       gmail_message("f2", "Sam Student <sam@school.edu>", "Fwd: New announcement", canvas),
                       gmail_message("f3", "Dana Lee <dlee@school.edu>", "Office hours", plain)])
    mail.fetch(conn, cfg, NOW, session=gmail)
    rows = {r["external_id"]: r for r in conn.execute("SELECT * FROM messages")}
    assert (rows["f1"]["sender"], rows["f1"]["address"], rows["f1"]["subject"]) == ("Lee, Dana", "dlee@school.edu", "Lab 3 moved")
    assert rows["f1"]["text"] == "The lab report is now due Friday."
    assert rows["f2"]["noise"] == "Canvas notification"  # recognized through the forward
    assert rows["f3"]["sender"] == "Dana Lee" and rows["f3"]["text"] == "Hi Sam,\n\nSee you at office hours."


# ---- recorded GroupMe ---------------------------------------------------------------------------------------


class FakeGroupMe:
    def __init__(self, groups, msgs):
        self.groups, self.msgs, self.calls = groups, msgs, []

    def get(self, path, **params):
        self.calls.append((path, params))
        if path == "/groups":
            return 200, self.groups
        gid = path.split("/")[2]
        allm = sorted(self.msgs.get(gid, []), key=lambda m: m["created_at"])
        if "after_id" in params:
            ids = [m["id"] for m in allm]
            after = allm[ids.index(params["after_id"]) + 1:] if params["after_id"] in ids else []
            return (304, None) if not after else (200, {"messages": after[: params.get("limit", 20)]})
        return 200, {"messages": list(reversed(allm))[: params.get("limit", 20)]}


def gm(mid, text, hours_ago, user="u1", name="Sam", system=False):
    return {"id": mid, "text": text, "created_at": int((NOW - timedelta(hours=hours_ago)).timestamp()), "user_id": user,
            "name": name, "sender_type": "system" if system else "user", "attachments": []}


def test_groupme_reads_new_messages_skips_muted_and_own(env):
    cfg, conn = env
    api = FakeGroupMe(
        [{"id": "1", "name": "Sigma Chi"}, {"id": "2", "name": "Memes"}],
        {"1": [gm("10", "old news", 100), gm("11", "Meeting moved to the soccer fields at 6", 3),
               gm("12", "I'll be there", 2, user="me"), gm("13", "Sam changed the topic", 1, system=True)],
         "2": [gm("20", "lol", 1)]},
    )
    cfg.muted_groups = ["2"]
    counts = groupme.fetch(conn, cfg, NOW, api=api)
    assert counts["kept"] == 1 and counts["muted"] == 1
    row = conn.execute("SELECT * FROM messages WHERE source = 'groupme'").fetchone()
    assert row["channel"] == "Sigma Chi" and "soccer fields" in row["text"]
    # New messages since the last one seen; none from the muted group.
    api.msgs["1"].append(gm("14", "Bring cleats", 0.5))
    groupme.fetch(conn, cfg, NOW, api=api)
    assert [r["external_id"] for r in conn.execute("SELECT external_id FROM messages ORDER BY id")] == ["11", "14"]
    assert not any(c[0].startswith("/groups/2/") for c in api.calls)


# ---- picking out what matters -----------------------------------------------------------------------------


def _msg(conn, mid, text, source="email", channel=None):
    messages.store(conn, {"source": source, "external_id": mid, "sender": "Dr. Lee", "subject": "s", "channel": channel,
                          "sent_at": NOW.isoformat(), "text": text, "link": f"https://mail/{mid}"})


def _canvas_item(conn, title, due, kind="assignment"):
    cur = conn.execute(
        "INSERT INTO items (source, external_id, course_code, kind, title, due_at, first_seen, last_seen) VALUES ('canvas_feed', ?, 'PHYS-110', ?, ?, ?, 'x', 'x')",
        (title, kind, title, due.isoformat(timespec="minutes")),
    )
    return int(cur.lastrowid)


def answer(*per_message):
    return lambda prompt, payload: json.dumps({"messages": [{"n": i + 1, **m} for i, m in enumerate(per_message)]})


def test_facts_become_deadlines_and_happenings_and_text_is_dropped(env):
    cfg, conn = env
    lab = _canvas_item(conn, "Lab 3 report", NOW + timedelta(days=5))
    hw = _canvas_item(conn, "Homework 4", NOW + timedelta(days=3))
    for i in range(5):
        _msg(conn, f"m{i}", f"text {i}")
    ask = answer(
        {"matters": True, "facts": [{"type": "deadline", "title": "Lab 3 report", "when": (NOW + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                                     "about": f"item:{lab}", "change": "moved", "summary": "Lab 3 is now due Friday."}]},
        {"matters": True, "facts": [{"type": "deadline", "title": "Homework 4", "when": (NOW + timedelta(days=3)).strftime("%Y-%m-%d"),
                                     "course": "PHYS-110", "about": f"item:{hw}", "change": "same"}]},
        {"matters": True, "facts": [{"type": "deadline", "title": "Problem set 5", "when": (NOW + timedelta(days=4)).strftime("%Y-%m-%d"),
                                     "course": "PHYS-110", "kind": "assignment", "change": "new", "summary": "PS5 posted."}]},
        {"matters": True, "facts": [{"type": "event", "title": "Exam review session", "when": "2026-10-08T19:00", "where": "Hall 2",
                                     "course": "PHYS-110", "change": "new"},
                                    {"type": "action", "title": "Register for spring classes", "when": "2026-10-13", "change": "new"}]},
        {"matters": False, "facts": []},
    )
    counts = messages.read_new(conn, cfg, NOW, ask=ask)
    assert counts["read"] == 5 and counts["facts"] == 4
    # Moved: the email's date shows in place of Canvas's, and the move is an urgent change.
    shown = conn.execute("SELECT * FROM items WHERE merged_into IS NULL AND title = 'Lab 3 report'").fetchall()
    assert len(shown) == 1 and shown[0]["source"] == "email" and shown[0]["due_at"].startswith((NOW + timedelta(days=2)).date().isoformat())
    assert conn.execute("SELECT urgency FROM changes WHERE field = 'due_at'").fetchone()["urgency"] == "urgent"
    # A reminder of a known deadline adds nothing; a new one joins the list and is flagged.
    assert conn.execute("SELECT COUNT(*) FROM items WHERE title = 'Homework 4'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM changes WHERE field = 'new'").fetchone()[0] == 1
    hs = {h["title"]: h for h in happenings.upcoming(conn, cfg, NOW, 14)}
    assert hs["Exam review session"]["location"] == "Hall 2" and hs["Register for spring classes"]["kind"] == "action"
    # Facts, not mail.
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE text IS NOT NULL").fetchone()[0] == 0


def test_a_deadline_canvas_already_has_is_merged(env):
    cfg, conn = env
    due = (NOW + timedelta(days=6)).replace(hour=23, minute=59)
    _canvas_item(conn, "Homework 5", due)
    _msg(conn, "x", "HW5 due next week")
    messages.read_new(conn, cfg, NOW, ask=answer(
        {"matters": True, "facts": [{"type": "deadline", "title": "Homework 5", "when": due.strftime("%Y-%m-%d"), "course": "PHYS-110", "change": "new"}]}))
    visible = conn.execute("SELECT * FROM items WHERE title = 'Homework 5' AND merged_into IS NULL").fetchall()
    assert len(visible) == 1 and visible[0]["source"] == "canvas_feed"


def test_a_change_updates_its_happening(env):
    cfg, conn = env
    hid = happenings.add(conn, "event", "Chapter meeting", "2026-10-07T20:00", location="House", source="groupme", channel="Sigma Chi")
    _msg(conn, "g1", "moved to the soccer fields at 6", source="groupme", channel="Sigma Chi")
    messages.read_new(conn, cfg, NOW, ask=answer(
        {"matters": True, "facts": [{"type": "event", "title": "Chapter meeting", "when": "2026-10-07T18:00", "where": "Soccer fields",
                                     "about": f"happening:{hid}", "change": "moved", "summary": "Moved to the soccer fields at 6."}]}))
    h = conn.execute("SELECT * FROM happenings WHERE id = ?", (hid,)).fetchone()
    assert h["starts_at"] == "2026-10-07T18:00" and h["location"] == "Soccer fields" and h["urgent"] == 1
    assert conn.execute("SELECT COUNT(*) FROM happenings").fetchone()[0] == 1
    assert any("Changed: Chapter meeting" in x for x in happenings.conflicts(conn, cfg, NOW))


def test_reading_failures_retry_then_give_up_and_the_daily_limit_holds(env):
    cfg, conn = env
    _msg(conn, "f", "text")

    def broken(prompt, payload):
        raise ValueError("bad answer")

    for _ in range(3):
        messages.read_new(conn, cfg, NOW, ask=broken)
    assert conn.execute("SELECT state FROM messages").fetchone()["state"] == "failed"
    cfg.message_reads_per_day = 1
    _msg(conn, "g", "one")
    _msg(conn, "h", "two")
    messages.read_new(conn, cfg, NOW, ask=answer({"matters": False}, {"matters": False}))
    assert messages.waiting(conn) == 1


def test_prompt_carries_context_and_messages_go_on_standard_input(env):
    cfg, conn = env
    _canvas_item(conn, "Exam 2", NOW + timedelta(days=2), kind="exam")
    _msg(conn, "p", "Exam 2 moved")
    seen = {}

    def ask(prompt, payload):
        seen.update(prompt=prompt, payload=payload)
        return '```json\n{"messages": [{"n": 1, "matters": false}]}\n```'

    messages.read_new(conn, cfg, NOW, ask=ask)
    assert "Exam 2 (exam)" in seen["prompt"] and "PHYS-110 (Physics)" in seen["prompt"] and "Exam 2 moved" not in seen["prompt"]
    assert json.loads(seen["payload"])[0]["text"] == "Exam 2 moved"


# ---- the Oso calendar ------------------------------------------------------------------------------------


class FakeCalendar:
    def __init__(self):
        self.events: dict[str, dict] = {"his": {"id": "his", "summary": "Calculus lecture", "start": {"dateTime": "2026-10-07T09:00:00-04:00"},
                                                "end": {"dateTime": "2026-10-07T09:50:00-04:00"}, "location": "Room 101"},
                                        "alert": {"id": "alert", "summary": "Oso: Physics: HW moved", "start": {"dateTime": "2026-10-07T12:00:00-04:00"},
                                                  "end": {"dateTime": "2026-10-07T12:30:00-04:00"}}}
        self.log: list[tuple[str, str]] = []
        self.n = 0

    def post(self, url, json=None):
        self.n += 1
        eid = f"e{self.n}"
        self.events[eid] = {**json, "id": eid}
        self.log.append(("add", eid))
        return Resp({"id": eid})

    def patch(self, url, json=None):
        eid = url.rsplit("/", 1)[1]
        self.events[eid].update(json)
        self.log.append(("move", eid))
        return Resp({"id": eid})

    def delete(self, url):
        eid = url.rsplit("/", 1)[1]
        self.events.pop(eid, None)
        self.log.append(("remove", eid))
        return Resp(status=204)

    def get(self, url, params=None):
        items = []
        for e in self.events.values():
            s = e["start"]
            items.append({**e, "start": s if "date" in s else {"dateTime": s["dateTime"] if s["dateTime"].count("-") > 2 or "+" in s["dateTime"] else s["dateTime"] + "-04:00"},
                          "end": e["end"] if "date" in e["end"] else {"dateTime": e["end"]["dateTime"] if e["end"]["dateTime"].count("-") > 2 else e["end"]["dateTime"] + "-04:00"}})
        return Resp({"items": items})


def test_calendar_adds_moves_and_cancels_only_its_own_events_and_reads_everything_back(env):
    cfg, conn = env
    cal = FakeCalendar()
    hid = happenings.add(conn, "event", "Chapter meeting", "2026-10-07T20:00", location="House", source="groupme", channel="Sigma Chi")
    happenings.add(conn, "action", "Register for spring classes", "2026-10-13", source="email", sender="Registrar")
    c = happenings.sync_calendar(conn, cfg, NOW, cal, "cal")
    assert c["added"] == 1  # actions don't go on the calendar
    eid = conn.execute("SELECT event_id FROM happenings WHERE id = ?", (hid,)).fetchone()["event_id"]
    assert cal.events[eid]["extendedProperties"]["private"]["oso"] == f"happening:{hid}"
    happenings.change(conn, hid, NOW + timedelta(minutes=1), starts_at="2026-10-07T18:00", location="Soccer fields")
    happenings.sync_calendar(conn, cfg, NOW + timedelta(minutes=2), cal, "cal")
    assert cal.events[eid]["start"]["dateTime"].startswith("2026-10-07T18:00") and cal.events[eid]["location"] == "Soccer fields"
    happenings.change(conn, hid, NOW + timedelta(minutes=3), canceled=True)
    happenings.sync_calendar(conn, cfg, NOW + timedelta(minutes=4), cal, "cal")
    assert eid not in cal.events
    assert {e for _, e in cal.log} == {eid}  # his lecture and Oso's alert were never touched
    titles = [e["title"] for e in happenings.schedule(conn, cfg, NOW, 0)]
    assert titles == ["Calculus lecture"]  # his own event is read back; the deadline alert is not schedule


def test_today_has_the_schedule_conflicts_and_coming_up(env):
    cfg, conn = env
    _canvas_item(conn, "Exam 2", datetime(2026, 10, 8, 10, 0, tzinfo=TZ), kind="exam")
    happenings.add(conn, "event", "Mixer", "2026-10-07T21:00", ends_at="2026-10-07T23:00", source="groupme", channel="Sigma Chi")
    happenings.add(conn, "event", "Study group", "2026-10-07T21:30", source="email", sender="Dr. Lee")
    happenings.add(conn, "event", "Tailgate", "2026-10-10T12:00", location="Stadium", source="chat")
    happenings.add(conn, "action", "Register for spring classes", "2026-10-08", source="email", sender="Registrar")
    from oso import tasks

    tasks.import_actions(conn, cfg, NOW)  # things to do are tasks
    text = today.render(conn, cfg, NOW)
    assert "## Today's schedule" in text and "9:00 PM–11:00 PM: Mixer (GroupMe, Sigma Chi)" in text
    assert "Mixer (Wed Oct 07, 9:00 PM–11:00 PM) is the evening before Physics Exam 2 (Thu Oct 08)." in text
    assert "Mixer and Study group overlap" in text
    assert "## Tasks\n- Register for spring classes (by Thu Oct 08) [from email]" in text
    assert "## Coming up" in text and "Sat Oct 10, 12:00 PM: Tailgate at Stadium (added in chat)" in text


def test_briefing_weighs_the_trade_off():
    text = (Path(__file__).parent.parent / "service" / "oso" / "skills" / "oso-briefing.md").read_text()
    assert "Heads up" in text and "trade-off" in text and "he decides" in text


def test_claude_reads_messages_with_no_tools(env, monkeypatch):
    """Messages come from strangers, so the Claude that reads them must have no tools and no MCP servers."""
    cfg, _ = env
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "[]", ""

    monkeypatch.setattr(messages.subprocess, "run", lambda argv, **kw: seen.update(argv=argv, kw=kw) or Done())
    messages.ask_claude("claude", cfg, "the prompt", "[]")
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv and "--mcp-config" not in argv
    assert seen["kw"]["input"] == "[]"
