from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import db, merge, sync, today
from oso.config import Config, Course
from oso.db import Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


def item(ext, title, due, source="canvas_feed", kind="assignment", course="MATH-101-001"):
    return Item(source=source, external_id=ext, kind=kind, title=title, due_at=due, course_code=course)


def test_new_update_change_and_delete(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        hw = item("a1", "Homework 1", NOW + timedelta(days=2))
        counts = merge.apply(conn, [hw], "canvas_feed", NOW)
        assert counts["new"] == 1

        hw.due_at = NOW + timedelta(days=3)
        counts = merge.apply(conn, [hw], "canvas_feed", NOW)
        assert counts["updated"] == 1 and counts["changed"] == 1
        change = conn.execute("SELECT field, urgency FROM changes").fetchone()
        assert change["field"] == "due_at" and change["urgency"] == "urgent"

        counts = merge.apply(conn, [], "canvas_feed", NOW)
        assert counts["deleted"] == 1
        assert conn.execute("SELECT deleted_at FROM items").fetchone()["deleted_at"] is not None


def test_user_override_survives_sync(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        hw = item("a1", "Homework 1", NOW + timedelta(days=2))
        merge.apply(conn, [hw], "canvas_feed", NOW)
        conn.execute("UPDATE items SET user_status = 'done', user_title = 'HW 1 (my name)'")
        merge.apply(conn, [hw], "canvas_feed", NOW)
        row = conn.execute(f"SELECT {db.EFFECTIVE} FROM items").fetchone()
        assert row["status"] == "done"
        assert row["title"] == "HW 1 (my name)"


def test_duplicate_across_sources_is_linked(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        due = NOW + timedelta(days=5)
        merge.apply(conn, [item("s1", "Homework 2", due, source="syllabus")], "syllabus", NOW)
        merge.apply(conn, [item("c1", "HW 2", due.replace(hour=23, minute=59))], "canvas_feed", NOW)
        rows = conn.execute("SELECT source, merged_into FROM items ORDER BY id").fetchall()
        assert rows[0]["merged_into"] is None
        assert rows[1]["merged_into"] == 1


def test_today_renders_sections(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", timezone="America/New_York", courses=[Course("MATH-101-001", "Calculus I", "Calculus I")])
    with db.connect(tmp_path / "t.sqlite") as conn:
        merge.apply(
            conn,
            [
                item("a1", "Homework 1", NOW - timedelta(days=1)),
                item("a2", "Homework 2", NOW + timedelta(hours=6)),
                item("a3", "Midterm 1", NOW + timedelta(days=10), kind="exam"),
            ],
            "canvas_feed",
            NOW,
        )
        run = db.record_sync(conn, "canvas_feed")
        db.finish_sync(conn, run, ok=True, items_seen=3)
        path = today.write(conn, cfg, NOW)
    text = path.read_text()
    assert "## Overdue" in text and "Homework 1" in text
    assert "## Due today" in text and "Homework 2" in text
    assert "Midterm 1" in text and "in 10 days" in text
    assert "**Calculus I**" in text
    assert "Canvas calendar feed is up to date" in text


def test_a_broken_today_page_is_replaced_by_a_sentence_and_nothing_else_is_lost(tmp_path: Path, monkeypatch):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("MATH-101", "Calculus", "Calculus")])
    cfg.vault.mkdir()
    db_file = tmp_path / "oso.sqlite"
    monkeypatch.setattr(db, "db_path", lambda: db_file)
    with db.connect() as conn:
        merge.apply(conn, [item("a1", "HW 1", NOW + timedelta(days=3))], "canvas_feed", NOW)

    def broken(conn, cfg, now):
        raise TypeError("can't compare offset-naive and offset-aware datetimes")

    monkeypatch.setattr(today, "write", broken)
    with db.connect() as conn:
        assert sync._safe(lambda: sync._write_today(conn, cfg, NOW), None) is None
    text = (cfg.vault / "Today.md").read_text(encoding="utf-8")
    assert text.startswith("# Today") and "couldn't build today's page" in text and "Traceback" not in text
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_error_sentences_carry_no_address_and_no_false_login_alarm():
    import requests

    e = requests.exceptions.SSLError("HTTPSConnectionPool(host='x.instructure.com', port=443): Max retries exceeded with url: /feeds/calendars/user_SECRET.ics (Caused by SSLError)")
    assert sync.plain_error(e) == "could not reach the source; check the internet connection"
    text = sync.plain_error(requests.HTTPError("500 Server Error: Internal for url: https://x.instructure.com/feeds/calendars/user_SECRET.ics"))
    assert "SECRET" not in text and "user_" not in text and "(address)" in text
    assert sync.plain_error(RuntimeError("could not open 4015.pdf")) == "could not open 4015.pdf"
    assert sync.plain_error(RuntimeError("401 Client Error: Unauthorized for url: https://x/feed?token=SECRET")) == "the source rejected the login; it may need to be set up again"
    assert "check the internet" in sync.plain_error(requests.ConnectionError("https://x/feeds/SECRET.ics"))
