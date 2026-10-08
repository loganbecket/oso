"""Class times: saved from setup, kept three weeks ahead on the calendar, one meeting canceled or moved by a message,
Canvas announcements read like email, and courses with no times called out."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import classes, config as cfgmod, db, happenings, messages, rules, today
from oso.config import Config, Course

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 8, 7, 0, tzinfo=TZ)  # a Thursday
PHYS = [{"kind": "class", "days": "TR", "starts": "9:30 AM", "ends": "10:45 AM", "location": "Baylor Sciences 101"},
        {"kind": "lab", "days": "W", "starts": "14:00", "ends": "16:50", "location": "Lab 210"}]


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    cfg = Config(vault=tmp_path / "vault", timezone="America/Chicago",
                 courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics"), Course("MATH-201", "Calculus II", "2026 Fall/Calculus II")])
    cfg.vault.mkdir()
    cfgmod.save(cfg)
    with db.connect() as conn:
        messages.ensure(conn)
        yield cfg, conn


def class_events(conn, active=True):
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM happenings WHERE source = 'class' {'AND status = ' + chr(39) + 'active' + chr(39) if active else ''} ORDER BY starts_at")]


def test_class_times_go_on_the_calendar_three_weeks_ahead(env):
    cfg, conn = env
    out = classes.set_times(conn, cfg, "PHYS-110", PHYS, "2026-08-24", "2026-12-04", ["2026-10-15", "2026-11-25"], NOW)
    assert out["meetings"] == 2
    evs = class_events(conn)
    assert evs[0]["title"] == "Physics" and evs[0]["starts_at"] == "2026-10-08T09:30" and evs[0]["ends_at"] == "2026-10-08T10:45"
    assert evs[0]["location"] == "Baylor Sciences 101"
    assert "2026-10-14T14:00" in [e["starts_at"] for e in evs if e["title"] == "Physics lab"]
    assert not any(e["starts_at"].startswith("2026-10-15") for e in evs)  # no class that day
    assert max(e["starts_at"] for e in evs) <= "2026-10-29T23:59"
    assert classes.extend(conn, cfg, NOW) == 0  # nothing twice
    assert classes.extend(conn, cfg, NOW + timedelta(days=7)) == 3  # rolls forward a week: T, W, R
    assert "Physics" in [e["title"] for e in happenings.schedule(conn, cfg, NOW, 0)]


def test_one_meeting_canceled_by_a_message_comes_off_and_stays_off(env):
    cfg, conn = env
    classes.set_times(conn, cfg, "PHYS-110", PHYS, "2026-08-24", "2026-12-04", [], NOW)
    today_class = class_events(conn)[0]
    messages.store(conn, {"source": "email", "external_id": "m1", "sender": "Dr. Lee", "subject": "No class today",
                          "sent_at": NOW.isoformat(), "text": "Class is canceled today."})
    seen = {}

    def ask(prompt, payload):
        seen["prompt"] = prompt
        return ('{"messages": [{"n": 1, "matters": true, "facts": [{"type": "event", "title": "Physics", "when": "2026-10-08T09:30", '
                f'"about": "happening:{today_class["id"]}", "change": "canceled", "urgent": true, "summary": "Physics is canceled today."}}]}}]}}')

    messages.read_new(conn, cfg, NOW, ask=ask)
    assert f"happening:{today_class['id']} PHYS-110 Physics 2026-10-08T09:30 at Baylor Sciences 101" in seen["prompt"]
    row = conn.execute("SELECT * FROM happenings WHERE id = ?", (today_class["id"],)).fetchone()
    assert row["status"] == "canceled" and row["synced_at"] is None  # the calendar removes it on this check
    classes.extend(conn, cfg, NOW + timedelta(hours=1))
    assert not any(e["starts_at"] == "2026-10-08T09:30" for e in class_events(conn))
    assert "Canceled: Physics" in today.render(conn, cfg, NOW)


def test_class_moved_online_for_one_day(env):
    cfg, conn = env
    classes.set_times(conn, cfg, "PHYS-110", PHYS, "2026-08-24", "2026-12-04", [], NOW)
    hid = class_events(conn)[0]["id"]
    messages.apply_fact(conn, cfg, NOW, {"source": "canvas", "id": 1, "external_id": "a1", "sender": "Physics"},
                        {"type": "event", "title": "Physics", "when": "2026-10-08T09:30", "where": "Online", "about": f"happening:{hid}", "change": "moved"})
    row = conn.execute("SELECT * FROM happenings WHERE id = ?", (hid,)).fetchone()
    assert row["location"] == "Online" and row["status"] == "active"
    assert conn.execute("SELECT location FROM happenings WHERE source = 'class' AND starts_at = '2026-10-13T09:30'").fetchone()[0] == "Baylor Sciences 101"


def test_new_class_times_replace_the_old_but_not_a_canceled_meeting(env):
    cfg, conn = env
    classes.set_times(conn, cfg, "PHYS-110", PHYS, "2026-08-24", "2026-12-04", [], NOW)
    canceled = class_events(conn)[0]["id"]
    happenings.change(conn, canceled, NOW, canceled=True, note="Canceled.")
    classes.set_times(conn, cfg, "PHYS-110", [{"days": "TR", "starts": "11:00", "ends": "12:15"}], "2026-08-24", "2026-12-04", [], NOW)
    starts = [e["starts_at"] for e in class_events(conn)]
    assert "2026-10-13T09:30" not in starts and "2026-10-13T11:00" in starts
    assert "2026-10-08T11:00" in starts  # the new time that day
    assert conn.execute("SELECT status FROM happenings WHERE id = ?", (canceled,)).fetchone()[0] == "canceled"
    assert not any(e["title"] == "Physics lab" for e in class_events(conn))


def test_bad_times_are_turned_away_in_plain_words(env):
    cfg, conn = env
    with pytest.raises(ValueError, match="which days"):
        classes.set_times(conn, cfg, "PHYS-110", [{"days": "sometimes", "starts": "9", "ends": "10"}], "2026-08-24", "2026-12-04")
    with pytest.raises(ValueError, match="before it starts"):
        classes.set_times(conn, cfg, "PHYS-110", [{"days": "MWF", "starts": "10:00", "ends": "9:00"}], "2026-08-24", "2026-12-04")
    assert classes._days("Tu/Th") == "TR" and classes._days("Mon Wed Fri") == "MWF" and classes._hhmm("2 p.m.") == "14:00"


def test_courses_without_class_times_are_called_out(env):
    cfg, conn = env
    classes.set_times(conn, cfg, "PHYS-110", PHYS, "2026-08-24", "2026-12-04", [], NOW)
    text = today.render(conn, cfg, NOW)
    assert "## Class times\n- Oso doesn't know when Calculus II meets" in text


def test_study_blocks_avoid_classes(env):
    cfg, conn = env
    classes.set_times(conn, cfg, "PHYS-110", [{"days": "MTWRF", "starts": "8:00", "ends": "12:00"}], "2026-08-24", "2026-12-04", [], NOW)
    assert rules.open_slot(conn, cfg, NOW, NOW.date() + timedelta(days=1), 60).strftime("%H:%M") == "12:00"


def test_canvas_announcements_are_read_like_email(env, monkeypatch):
    cfg, conn = env
    from oso import sync

    class Api:
        new_announcements = [{"source": "canvas", "external_id": "77", "sender": "Physics", "subject": "Important announcement",
                              "channel": "PHYS-110", "sent_at": NOW.isoformat(timespec="minutes"),
                              "text": "Please bring your Arduino kit to lab.", "link": "https://canvas/x"}]

    sync._store_announcements(conn, Api())
    batches = messages._batches(conn)
    assert [what for what, _ in batches] == ["Canvas announcements and inbox messages from his instructors"]
    got = {}

    def ask(prompt, payload):
        got["payload"] = payload
        return ('{"messages": [{"n": 1, "matters": true, "facts": [{"type": "action", "title": "Bring Arduino kit to Physics lab", '
                '"when": "2026-10-08T14:00", "course": "PHYS-110", "about": null, "change": "new", "urgent": true, "summary": "Bring the kit."}]}]}')

    messages.read_new(conn, cfg, NOW, ask=ask)
    assert "Arduino kit" in got["payload"]
    from oso import tasks

    tasks.import_actions(conn, cfg, NOW)
    assert "- Bring Arduino kit to Physics lab (today) [from canvas]" in today.render(conn, cfg, NOW)
