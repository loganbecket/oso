"""Phase 5 of the review: tools answer in sentences, settings carry their own model, Google calls time out, and
odd answers from Claude or old records do no harm."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import config as cfgmod, db, gcal, mcp_server, merge, messages
from oso.config import Config, Course
from oso.db import Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    cfg.vault.mkdir()
    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    return cfg


def test_item_tools_answer_in_sentences_and_add_item_returns_the_same_id_twice(env):
    first = mcp_server.add_item("PHYS-110", "Lab report", "assignment", due_at="2026-10-20")
    again = mcp_server.add_item("PHYS-110", "Lab report", "assignment", due_at="2026-10-20", weight=10)
    assert first["id"] == again["id"] and first["id"] > 0
    assert mcp_server.add_item("PHYS-110", "x", "homework")["note"].startswith("The kind must be")
    assert mcp_server.add_item("PHYS-110", "x", "exam", due_at="next Tuesday")["note"] == mcp_server.BAD_DATE
    assert mcp_server.update_status(999, "done")["note"] == "No item 999."
    assert mcp_server.update_status(first["id"], "finished")["note"].startswith("The status must be")
    assert mcp_server.set_due_date(999, "2026-10-21")["note"] == "No item 999."
    assert mcp_server.set_due_date(first["id"], "soon")["note"] == mcp_server.BAD_DATE
    assert mcp_server.set_weight(999, 5)["note"] == "No item 999."
    assert mcp_server.record_grade(999, 9, 10)["note"] == "No item 999."
    assert mcp_server.mark_alert_reported(999)["note"] == "No alert 999."
    assert mcp_server.update_status(first["id"], "done") == {"id": first["id"], "status": "done"}


def test_calendar_tools_refuse_a_date_they_cannot_read(env):
    assert mcp_server.add_to_calendar("Tailgate", "Saturday noon")["note"] == mcp_server.BAD_DATE
    assert mcp_server.change_calendar(happening=1, start="later")["note"] == mcp_server.BAD_DATE
    assert mcp_server.open_time(60, "tomorrow")["note"] == mcp_server.BAD_DATE
    assert mcp_server.open_time(60, "2026-10-09", not_before="9am")["note"] == mcp_server.BAD_DATE


def test_the_background_model_is_its_own_setting(tmp_path: Path, monkeypatch):
    cfg = Config(vault=tmp_path, transcribe_model="haiku", background_model="opus")
    path = tmp_path / "config.toml"
    cfgmod.save(cfg, path)
    back = cfgmod.load(path)
    assert back.transcribe_model == "haiku" and back.background_model == "opus"
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "[]", ""

    monkeypatch.setattr(messages.subprocess, "run", lambda argv, **kw: seen.update(argv=argv) or Done())
    messages.ask_claude("claude", back, "the prompt", "[]")
    assert seen["argv"][seen["argv"].index("--model") + 1] == "opus"


def test_every_google_call_gets_a_timeout():
    calls = []

    class Fake:
        def request(self, method, url, *a, **kw):
            calls.append(kw)

    s = gcal.timed(Fake())
    s.request("GET", "https://example")
    s.request("GET", "https://example", timeout=5)
    assert calls[0]["timeout"] == gcal.GOOGLE_TIMEOUT and calls[1]["timeout"] == 5


def test_old_change_records_are_tidied(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        merge.apply(conn, [Item(source="canvas_feed", external_id="a", kind="assignment", title="HW", due_at=NOW, course_code="C")], "canvas_feed", NOW)
        conn.execute("INSERT INTO changes (item_id, field, detected_at) VALUES (1, 'due_at', ?)", (db.since(NOW, timedelta(days=400)),))
        conn.execute("INSERT INTO changes (item_id, field, detected_at) VALUES (1, 'due_at', ?)", (db.since(NOW, timedelta(days=4)),))
        conn.execute("INSERT INTO canvas_events (at, course, text) VALUES (?, 'C', 'old')", (db.since(NOW, timedelta(days=400)),))
        assert db.prune(conn, NOW) == 2
        assert conn.execute("SELECT COUNT(*) FROM changes").fetchone()[0] == 1
