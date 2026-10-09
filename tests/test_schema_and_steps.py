"""One schema for the whole database, readers beside a writer, steps that stand or fall alone, and the small
rules that keep a check honest: believable deletions, one name per course, and time windows in UTC."""

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import db, merge, schema, sync
from oso.config import Config, Course
from oso.db import Item

NOW = datetime(2026, 10, 5, 8, 0, tzinfo=ZoneInfo("America/New_York"))


def test_an_old_database_is_brought_up_to_date_once(tmp_path: Path):
    path = tmp_path / "old.sqlite"
    raw = sqlite3.connect(path)
    raw.executescript(db.SCHEMA.replace("    category      TEXT,\n", ""))  # v0.18.2 shape: no category column, no other tables
    raw.commit()
    raw.close()
    with db.connect(path) as conn:
        assert schema.current(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        assert "category" in cols
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"happenings", "messages", "quizzes", "course_topics", "clip_log", "meta", "step_failures", "site_pages"} <= tables
        assert schema.apply(conn) is False  # nothing to do the second time


def test_a_reader_is_not_blocked_by_a_writer_and_a_second_writer_waits(tmp_path: Path):
    path = tmp_path / "t.sqlite"
    with db.connect(path):
        pass
    writer = sqlite3.connect(path, timeout=30)
    writer.execute("INSERT INTO courses (code, name, folder, created_at) VALUES ('A', 'A', 'A', 'x')")  # open transaction
    reader = sqlite3.connect(path, timeout=30)
    assert reader.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0  # WAL: reads go on
    done = {}

    def second_writer():
        c = sqlite3.connect(path, timeout=30)
        t = time.monotonic()
        c.execute("INSERT INTO courses (code, name, folder, created_at) VALUES ('B', 'B', 'B', 'x')")
        c.commit()
        done["waited"] = time.monotonic() - t

    th = threading.Thread(target=second_writer)
    th.start()
    time.sleep(0.5)
    writer.commit()
    th.join(10)
    assert "waited" in done and done["waited"] >= 0.3  # it waited instead of failing with "database is locked"
    assert reader.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 2


def test_a_failed_step_is_rolled_back_and_written_down_until_it_works(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        def half_done():
            conn.execute("INSERT INTO courses (code, name, folder, created_at) VALUES ('X', 'X', 'X', 'x')")
            raise RuntimeError("the disk went away")

        assert sync._safe(half_done, 0, conn, "books") == 0
        assert conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0  # its half-done write is gone
        failures = db.step_failures(conn)
        assert [f["name"] for f in failures] == ["books"] and "disk went away" in failures[0]["error"]
        assert sync._safe(lambda: 1, 0, conn, "books") == 1
        assert db.step_failures(conn) == []


def item(ext, title, due, source="canvas_feed", kind="assignment", course="MATH-101"):
    return Item(source=source, external_id=ext, kind=kind, title=title, due_at=due, course_code=course)


def test_a_source_that_suddenly_returns_almost_nothing_is_not_believed(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        items = [item(f"a{i}", f"HW {i}", NOW + timedelta(days=i)) for i in range(10)]
        merge.apply(conn, items, "canvas_feed", NOW)
        c = merge.apply(conn, [], "canvas_feed", NOW)
        assert c["deleted"] == 0 and c["deletions_skipped"] == 10
        c = merge.apply(conn, items[:3], "canvas_feed", NOW)
        assert c["deleted"] == 0 and c["deletions_skipped"] == 7
        assert conn.execute("SELECT COUNT(*) FROM changes WHERE field = 'deleted'").fetchone()[0] == 0
        c = merge.apply(conn, items[:9], "canvas_feed", NOW)  # one item really gone
        assert c["deleted"] == 1 and "deletions_skipped" not in c


def test_one_name_per_course_whatever_the_source_calls_it(tmp_path: Path):
    cfg = Config(vault=tmp_path, courses=[Course("PHYS-110", "General Physics", "2026 Fall/Physics", term="2026 Fall"),
                                           Course("MATH-101", "Calculus", "Calculus")])
    for ref in ("PHYS-110", "phys 110", "PHYS110", "PHYS-110-001", "2026FA-PHYS-110", "General Physics", "physics"):
        assert cfg.resolve(ref) is not None and cfg.resolve(ref).code == "PHYS-110", ref
    assert cfg.resolve("MATH 101").code == "MATH-101" and cfg.resolve("CHEM-200") is None and cfg.resolve(None) is None
    with db.connect(tmp_path / "t.sqlite") as conn:
        merge.apply(conn, [item("f1", "HW 2", NOW + timedelta(days=2), course="PHYS 110")], "canvas_feed", NOW, cfg=cfg)
        merge.apply(conn, [item("a1", "Homework 2", NOW + timedelta(days=2), source="canvas_api", course="PHYS-110-001")], "canvas_api", NOW, cfg=cfg)
        rows = conn.execute("SELECT course_code, merged_into FROM items ORDER BY id").fetchall()
        assert [r["course_code"] for r in rows] == ["PHYS-110", "PHYS-110"]
        assert rows[1]["merged_into"] == 1  # the same homework from two sources is one item


def test_time_windows_are_in_utc_whatever_the_time_zone():
    now = datetime(2026, 10, 5, 3, 0, tzinfo=ZoneInfo("Europe/Athens"))  # UTC+3
    since = db.since(now, timedelta(hours=2))
    detected = "2026-10-04T23:30:00+00:00"  # 90 minutes ago, as detected_at stores it
    assert since <= detected  # inside the window; with a local-offset string the window would have been empty
    assert since.endswith("+00:00")
