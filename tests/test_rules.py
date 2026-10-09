"""Rules: how rules reaching the commands, when rules firing once per thing, blocks following their exam, message
rules, Claude in the background with only Oso's tools, edited notes reread, and fresh start erasing them."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import config as cfgmod, db, fresh, happenings, instructions, messages, notes, rules, skillsync, today
from oso.config import Config, Course

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=TZ)  # a Thursday
EXAM_RULE = {"watch": "item", "kinds": ["exam"], "days_before": 3, "do": "block", "minutes": 180, "title": "Study for {title}"}


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    cfg = Config(vault=tmp_path / "vault", timezone="America/Chicago", quiet_hours="23:00-07:00",
                 courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    cfg.vault.mkdir()
    cfgmod.save(cfg)
    with db.connect() as conn:
        messages.ensure(conn)
        rules.ensure(conn)
        yield cfg, conn


def add_item(conn, title, kind, due: datetime, ext=None) -> int:
    cur = conn.execute(
        "INSERT INTO items (source, external_id, course_code, kind, title, due_at, first_seen, last_seen) VALUES ('canvas_feed', ?, 'PHYS-110', ?, ?, ?, 'x', 'x')",
        (ext or title, kind, title, due.isoformat(timespec="minutes")),
    )
    return int(cur.lastrowid)


def blocks(conn, active=True):
    q = "SELECT * FROM happenings WHERE source = 'rule'" + (" AND status = 'active'" if active else "")
    return [dict(r) for r in conn.execute(q + " ORDER BY id")]


def no_claude(*a):
    raise AssertionError("Claude should not be needed")


def test_how_rule_reaches_its_command_and_everything_reaches_all(env):
    cfg, conn = env
    rules.save(cfg, conn, "Briefing as bullets", "Give me the briefing as bullet highlights.", "how", NOW, applies_to="oso-briefing")
    rules.save(cfg, conn, "Short answers", "Keep answers to a few sentences.", "how", NOW, applies_to="everything")
    briefing = rules.with_rules(cfg, "oso-briefing", skillsync.instructions(cfg, "oso-briefing"))
    assert briefing.index("# Morning briefing") < briefing.index("## His rules")
    assert "- Give me the briefing as bullet highlights." in briefing and "- Keep answers to a few sentences." in briefing
    quiz = rules.with_rules(cfg, "oso-quiz", skillsync.instructions(cfg, "oso-quiz"))
    assert "bullet highlights" not in quiz and "a few sentences" in quiz
    vault_md = instructions.write(cfg).read_text()
    assert "## His rules" in vault_md and "a few sentences" in vault_md and "bullet highlights" not in vault_md
    note = cfg.vault / "Oso" / "Rules" / "Briefing as bullets.md"
    fm, body = notes.read_front_matter(note.read_text())
    assert fm["kind"] == "how" and "bullet highlights" in body
    rules.change(cfg, conn, "Briefing as bullets", NOW, paused=True)
    assert "bullet" not in rules.with_rules(cfg, "oso-briefing", "x")


def test_exam_rule_fires_once_per_new_exam_three_days_before(env):
    cfg, conn = env
    old = add_item(conn, "Exam 1", "exam", NOW + timedelta(days=10))
    rules.save(cfg, conn, "Study before exams", "When a new test date shows up, block three hours to study three days before.",
               "when", NOW, form=EXAM_RULE, apply_to_existing=False)
    add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))  # Monday
    add_item(conn, "HW 5", "assignment", NOW + timedelta(days=5))
    assert rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=no_claude)["fired"] == 1
    [b] = blocks(conn)
    assert b["title"] == "Study for Exam 2" and b["starts_at"] == "2026-10-16T07:00" and b["ends_at"] == "2026-10-16T10:00"
    rules.run(cfg, conn, NOW + timedelta(minutes=15), ask=no_claude, ask_claude=no_claude)
    assert len(blocks(conn)) == 1  # once per exam, and never for the one already there
    assert conn.execute("SELECT status FROM rule_fires WHERE target = ?", (f"item:{old}",)).fetchone()[0] == "skipped"
    text = today.render(conn, cfg, NOW)
    assert '## Your rules\n- Your rule "Study before exams" put Study for Exam 2 on the calendar, Fri Oct 16, 7 AM–10 AM.' in text
    fm, _ = notes.read_front_matter((cfg.vault / "Oso" / "Rules" / "Study before exams.md").read_text())
    assert fm["last_ran"].startswith("2026-10-08") and "Study for Exam 2" in fm["last_did"]


def test_existing_exams_get_the_rule_when_he_says_so(env):
    cfg, conn = env
    add_item(conn, "Exam 1", "exam", NOW + timedelta(days=10))
    rules.save(cfg, conn, "Study before exams", "x", "when", NOW, form=EXAM_RULE, apply_to_existing=True)
    rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=no_claude)
    assert [b["title"] for b in blocks(conn)] == ["Study for Exam 1"]


def test_block_avoids_classes_and_falls_back_to_an_earlier_day(env):
    cfg, conn = env
    rules.save(cfg, conn, "Study before exams", "x", "when", NOW, form=EXAM_RULE)
    for day in ("2026-10-16",):  # Friday is full: class all day
        conn.execute("INSERT INTO calendar_view (event_id, title, starts_at, ends_at, all_day, tag, read_at) VALUES (?, 'Lab', ?, ?, 0, '', 'x')",
                     ("e" + day, day + "T07:00", day + "T21:00"))
    conn.execute("INSERT INTO calendar_view (event_id, title, starts_at, ends_at, all_day, tag, read_at) VALUES ('c1', 'Physics', '2026-10-15T07:00', '2026-10-15T08:30', 0, '', 'x')")
    add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))
    rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=no_claude)
    [b] = blocks(conn)
    assert b["starts_at"] == "2026-10-15T08:30"
    assert "(Friday was full)" in today.render(conn, cfg, NOW)


def test_block_moves_with_the_exam_and_goes_when_it_is_canceled(env):
    cfg, conn = env
    rules.save(cfg, conn, "Study before exams", "x", "when", NOW, form=EXAM_RULE)
    exam = add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))
    rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=no_claude)
    conn.execute("UPDATE items SET due_at = ? WHERE id = ?", (datetime(2026, 10, 21, 10, 0, tzinfo=TZ).isoformat(timespec="minutes"), exam))
    rules.run(cfg, conn, NOW + timedelta(hours=1), ask=no_claude, ask_claude=no_claude)
    [b] = blocks(conn)
    assert b["starts_at"] == "2026-10-18T07:00" and b["synced_at"] is None  # the calendar hears on this check
    assert "moved Study for Exam 2 to Sun Oct 18, 7 AM–10 AM, because Exam 2 moved" in today.render(conn, cfg, NOW + timedelta(hours=1))
    conn.execute("INSERT INTO changes (item_id, field, old_value, new_value, detected_at) VALUES (?, 'canceled', 'x', 'canceled', 'x')", (exam,))
    rules.run(cfg, conn, NOW + timedelta(hours=2), ask=no_claude, ask_claude=no_claude)
    assert blocks(conn) == [] and blocks(conn, active=False)[0]["status"] == "canceled"
    assert len(conn.execute("SELECT * FROM rule_fires").fetchall()) == 1


def test_block_follows_an_exam_moved_by_email(env):
    cfg, conn = env
    rules.save(cfg, conn, "Study before exams", "x", "when", NOW, form=EXAM_RULE)
    exam = add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))
    rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=no_claude)
    moved = add_item(conn, "Exam 2", "exam", datetime(2026, 10, 20, 10, 0, tzinfo=TZ), ext="mail:1")
    conn.execute("UPDATE items SET merged_into = ? WHERE id = ?", (moved, exam))
    rules.run(cfg, conn, NOW + timedelta(hours=1), ask=no_claude, ask_claude=no_claude)
    [b] = blocks(conn)  # moved, not a second block for the "new" exam
    assert b["starts_at"].startswith("2026-10-17")


def test_email_sender_rule_blocks_an_hour_within_a_day(env):
    cfg, conn = env
    rules.save(cfg, conn, "Dean emails", "Any time I get an email from the dean, block an hour within a day to deal with it.", "when", NOW,
               form={"watch": "message", "sender": "dean@school.edu", "within_hours": 24, "do": "block", "minutes": 60, "title": "Deal with {title}"})
    for i, sender in enumerate(["Dean Smith <dean@school.edu>", "Club <club@school.edu>"]):
        messages.store(conn, {"source": "email", "external_id": f"m{i}", "sender": sender, "subject": "Housing form", "sent_at": NOW.isoformat(), "text": "Please sign."})
    assert rules.on_messages(cfg, conn, NOW, ask_claude=no_claude) == 1
    assert rules.on_messages(cfg, conn, NOW, ask_claude=no_claude) == 0
    [b] = blocks(conn)
    assert b["title"] == "Deal with Dean Smith <dean@school.edu>: Housing form" and b["starts_at"] == "2026-10-08T09:00"


def test_rule_needing_judgment_runs_claude_with_only_osos_tools(env, monkeypatch):
    cfg, conn = env
    rules.save(cfg, conn, "Advisor asks", "When my advisor emails, block time to do what the email asks.", "when", NOW,
               form={"watch": "message", "sender": "advisor", "do": "claude", "task": "Block time to do what the email asks."})
    messages.store(conn, {"source": "email", "external_id": "m1", "sender": "My Advisor <advisor@school.edu>", "subject": "Plan",
                          "sent_at": NOW.isoformat(), "text": "Draft your 4-year plan before Monday."})
    seen = {}

    def run(argv, **kw):
        seen["argv"], seen["env"], seen["input"] = argv, kw["env"], kw.get("input")
        class R:
            returncode, stdout, stderr = 0, "Blocked 2 hours on Saturday to draft the 4-year plan.", ""
        return R()

    monkeypatch.setattr(rules.shutil, "which", lambda name: "/bin/claude")
    monkeypatch.setattr(rules.subprocess, "run", run)
    assert rules.on_messages(cfg, conn, NOW) == 1
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
    assert argv[argv.index("--allowedTools") + 1] == "mcp__oso"
    assert "mcp__oso__update_oso" in argv[argv.index("--disallowedTools"):]
    mcp = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
    assert list(mcp["mcpServers"]) == ["oso"]
    assert "Draft your 4-year plan" in seen["input"]  # the prompt travels on standard input, not the command line
    fire = conn.execute("SELECT * FROM rule_fires").fetchone()
    assert seen["env"][rules.FIRE_ENV] == str(fire["id"]) and fire["status"] == "done"
    assert 'Your rule "Advisor asks": Blocked 2 hours on Saturday' in today.render(conn, cfg, NOW)


def test_claude_not_available_waits_and_says_so_once(env, monkeypatch):
    cfg, conn = env
    rules.save(cfg, conn, "Exam prep", "x", "when", NOW, form={"watch": "item", "kinds": ["exam"], "do": "claude", "task": "Plan study time."})
    add_item(conn, "Exam 2", "exam", NOW + timedelta(days=10))

    def down(prompt, fire):
        raise rules.NoClaude("Claude didn't answer on this computer (it may need signing in)")

    rules.run(cfg, conn, NOW, ask=no_claude, ask_claude=down)
    rules.run(cfg, conn, NOW + timedelta(minutes=15), ask=no_claude, ask_claude=down)
    text = today.render(conn, cfg, NOW)
    assert text.count("couldn't run yet") == 1 and "may need signing in" in text
    rules.run(cfg, conn, NOW + timedelta(minutes=30), ask=no_claude, ask_claude=lambda p, f: "Planned it.")
    assert conn.execute("SELECT status FROM rule_fires").fetchone()[0] == "done"


def test_edited_note_gets_a_new_form_before_it_runs(env):
    cfg, conn = env
    r = rules.save(cfg, conn, "Study before exams", "When a new test date shows up, block three hours three days before.", "when", NOW, form=EXAM_RULE)
    text = r.path.read_text().replace("block three hours three days before", "block two hours the day before")
    r.path.write_text(text)
    add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return json.dumps({"kind": "when", "form": {**EXAM_RULE, "days_before": 1, "minutes": 120}, "cannot": None})

    rules.run(cfg, conn, NOW, ask=ask, ask_claude=no_claude)
    assert len(asked) == 1 and "block two hours the day before" in asked[0]
    [b] = blocks(conn)
    assert b["starts_at"] == "2026-10-18T07:00" and b["ends_at"] == "2026-10-18T09:00"
    rules.run(cfg, conn, NOW + timedelta(minutes=15), ask=ask, ask_claude=no_claude)
    assert len(asked) == 1  # read once per version


def test_edited_note_waits_when_claude_cant_read_it(env):
    cfg, conn = env
    r = rules.save(cfg, conn, "Study before exams", "three hours", "when", NOW, form=EXAM_RULE)
    r.path.write_text(r.path.read_text().replace("three hours", "two hours"))
    add_item(conn, "Exam 2", "exam", datetime(2026, 10, 19, 10, 0, tzinfo=TZ))

    def down(prompt):
        raise rules.NoClaude("Claude Code isn't installed on this computer")

    rules.run(cfg, conn, NOW, ask=down, ask_claude=no_claude)
    assert blocks(conn) == []
    assert "couldn't read the new version yet" in today.render(conn, cfg, NOW)


def test_a_note_he_wrote_himself_is_read_and_given_an_id(env):
    cfg, conn = env
    d = cfg.vault / "Oso" / "Rules"
    d.mkdir(parents=True)
    (d / "Weather.md").write_text("Start every briefing with the weather.\n")
    rules.run(cfg, conn, NOW, ask=lambda p: '{"kind": "how", "applies_to": "oso-briefing", "cannot": null}', ask_claude=no_claude)
    fm, _ = notes.read_front_matter((d / "Weather.md").read_text())
    assert fm["id"].startswith("r") and fm["kind"] == "how"
    assert "with the weather" in rules.with_rules(cfg, "oso-briefing", "x")


def test_rule_oso_cant_follow_is_turned_down(env):
    cfg, conn = env
    with pytest.raises(rules.FormError, match="can only"):
        rules.save(cfg, conn, "Bitcoin", "Mine a bitcoin every time you update my calendar.", "when", NOW,
                   form={"watch": "calendar", "do": "mine bitcoin"})
    assert not (cfg.vault / "Oso" / "Rules").exists()
    skill = skillsync.shipped()["oso-rules"]
    assert "Mine a bitcoin" in skill and "save nothing" in skill


def test_conflicting_rule_is_narrowed_and_an_edit_that_conflicts_is_paused(env):
    cfg, conn = env
    skill = skillsync.shipped()["oso-rules"]
    assert "always tell me I'm on track" in skill and "narrowed" in skill and "which part and why" in skill
    r = rules.save(cfg, conn, "Study before exams", "three hours", "when", NOW, form=EXAM_RULE)
    r.path.write_text(r.path.read_text().replace("three hours", "three hours, and tell my professor I studied"))
    rules.run(cfg, conn, NOW, ask=lambda p: '{"kind": "when", "form": null, "cannot": "Oso never writes to your professor or to school."}',
              ask_claude=no_claude)
    assert rules.find(cfg, "Study before exams").paused
    assert "is paused: Oso never writes to your professor" in today.render(conn, cfg, NOW)


def test_fresh_start_erases_rules(env):
    cfg, conn = env

    rules.save(cfg, conn, "Short answers", "Keep answers short.", "how", NOW)
    paths = {p.relative_to(cfg.vault).as_posix() for p in fresh.plan(cfg)}
    assert "Oso" in paths  # the whole Oso folder, rules and all


def test_open_time_tool_and_rule_tools(env, monkeypatch):
    cfg, conn = env
    from oso import mcp_server

    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    assert mcp_server.save_rule("Dean emails", "x", "when", form={"watch": "message"}).startswith("Not done.")  # no yes yet
    saved = mcp_server.save_rule("Dean emails", "x", "when", form={"watch": "message", "sender": "dean", "do": "block", "minutes": 60}, confirmed=True)
    assert saved["saved"] == "Dean emails"
    assert mcp_server.save_rule("Bad", "x", "when", form={"watch": "item", "do": "block", "minutes": 5}, confirmed=True).startswith("Not saved:")
    assert [r["name"] for r in mcp_server.list_rules()] == ["Dean emails"]
    assert "Paused" in mcp_server.change_rule("Dean emails", paused=True)
    assert "Deleted" in mcp_server.change_rule("dean emails", delete=True)
    slot = mcp_server.open_time(60, "2026-12-01")
    assert slot["free"] and slot["start"] == "2026-12-01T07:00"


def test_claude_adding_to_the_calendar_for_a_rule_is_tracked(env, monkeypatch):
    cfg, conn = env
    from oso import mcp_server

    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    monkeypatch.setattr(happenings, "push", lambda *a: None)
    fire = rules._new_fire(conn, "r1", "item:1", "waiting")
    conn.commit()
    monkeypatch.setenv(rules.FIRE_ENV, str(fire))
    out = mcp_server.add_to_calendar("Draft plan", "2026-10-10T13:00", "2026-10-10T15:00")
    with db.connect() as c2:
        assert c2.execute("SELECT fire FROM rule_blocks WHERE happening = ?", (out["happening"],)).fetchone()[0] == fire
        assert c2.execute("SELECT source FROM happenings WHERE id = ?", (out["happening"],)).fetchone()[0] == "rule"


def test_offering_a_rule_is_in_every_conversation():
    from oso.tutor import SERVER_INSTRUCTIONS

    assert "Want me to keep that as a rule?" in SERVER_INSTRUCTIONS
