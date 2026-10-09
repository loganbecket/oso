from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import alerts, db, grades, merge
from oso.config import Config, Course
from oso.db import Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


def cfg(tmp_path: Path, **kw) -> Config:
    return Config(vault=tmp_path / "vault", timezone="America/New_York",
                  courses=[Course("MATH-101-001", "Calculus I", "Calculus I")], **kw)


def test_alerts_pending_mute_and_inbox(tmp_path: Path):
    c = cfg(tmp_path)
    with db.connect(tmp_path / "t.sqlite") as conn:
        hw = Item(source="canvas_feed", external_id="a1", kind="assignment", title="Homework 1",
                  due_at=NOW + timedelta(days=2), course_code="MATH-101-001")
        merge.apply(conn, [hw], "canvas_feed", NOW)
        hw.due_at = NOW + timedelta(days=4)
        merge.apply(conn, [hw], "canvas_feed", NOW)

        pend = alerts.pending(conn, c, NOW)
        assert len(pend) == 1 and "moved from" in pend[0]["message"] and pend[0]["deliver_after"] is None

        muted = cfg(tmp_path, muted_courses=["math-101-001"])
        assert alerts.pending(conn, muted, NOW) == []

        quiet = cfg(tmp_path, quiet_hours="22:00-09:00")
        assert alerts.pending(conn, quiet, NOW)[0]["deliver_after"] == "2026-10-05T09:00-04:00"

        assert alerts.write_inbox(conn, c, NOW) == 1
        assert alerts.write_inbox(conn, c, NOW) == 0
        text = (c.vault / "Oso" / "Alerts.md").read_text()
        assert "Calculus I" in text and "Homework 1 moved" in text
        assert "| due 2026-10-09T08:00-04:00 <!-- alert 1 -->" in text
        (c.vault / "Oso" / "Alerts.md").unlink()
        assert alerts.write_inbox(conn, quiet, NOW) == 1
        assert "(quiet until 2026-10-05 09:00)" in (c.vault / "Oso" / "Alerts.md").read_text()

        alerts.mark_reported(conn, pend[0]["alert_id"])
        assert alerts.pending(conn, c, NOW) == []


def test_quiet_until_overnight():
    c = Config(vault=Path("/tmp/x"), quiet_hours="22:00-07:00")
    late = datetime(2026, 10, 5, 23, 30, tzinfo=TZ)
    assert alerts.quiet_until(c, late) == datetime(2026, 10, 6, 7, 0, tzinfo=TZ)
    early = datetime(2026, 10, 6, 6, 0, tzinfo=TZ)
    assert alerts.quiet_until(c, early) == datetime(2026, 10, 6, 7, 0, tzinfo=TZ)
    assert alerts.quiet_until(c, datetime(2026, 10, 6, 12, 0, tzinfo=TZ)) is None


def test_grade_summary_and_what_if(tmp_path: Path):
    with db.connect(tmp_path / "t.sqlite") as conn:
        items = [
            Item(source="syllabus", external_id="h1", kind="assignment", title="HW 1", due_at=NOW, course_code="C", weight=30),
            Item(source="syllabus", external_id="h2", kind="assignment", title="HW 2", due_at=NOW, course_code="C", weight=30),
            Item(source="syllabus", external_id="m1", kind="exam", title="Midterm", due_at=NOW, course_code="C", weight=30),
            Item(source="syllabus", external_id="f1", kind="exam", title="Final", due_at=NOW, course_code="C", weight=40),
        ]
        merge.apply(conn, items, "syllabus", NOW)
        conn.execute("UPDATE items SET grade_points = 9, grade_max = 10 WHERE external_id = 'h1'")
        conn.execute("UPDATE items SET grade_points = 80, grade_max = 100 WHERE external_id = 'm1'")

        s = grades.summary(conn, "C")
        # Homework category: 1 of 2 graded at 90% -> earned 30*0.9*0.5 = 13.5, locked 15.
        # Exams category (weight 30, items midterm): graded 80% -> earned 24, locked 30.
        # Final is its own category (weight 40), ungraded.
        assert s["weight_graded_so_far"] == 45.0
        assert s["current_percent"] == round((13.5 + 24) / 45 * 100, 1)
        assert s["weight_remaining"] == 55.0

        w = grades.what_if(conn, "C", 90)
        assert w["needed_average_percent"] == round((90 - 37.5) / 55 * 100, 1)
        assert grades.what_if(conn, "C", 99)["note"].startswith("Not reachable")
        assert grades.what_if(conn, "C", 30)["note"].startswith("Already secured")


def test_two_categories_with_the_same_weight_stay_apart(tmp_path: Path):
    from oso import grades, merge
    from oso.db import Item

    with db.connect(tmp_path / "g.sqlite") as conn:
        now = datetime(2026, 10, 5, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        items = [Item(source="canvas_api", external_id="h1", kind="assignment", title="HW 1", due_at=now, course_code="C", weight=20, category="Homework"),
                 Item(source="canvas_api", external_id="l1", kind="assignment", title="Lab 1", due_at=now, course_code="C", weight=20, category="Labs"),
                 Item(source="canvas_api", external_id="e1", kind="exam", title="Exam 1", due_at=now, course_code="C", weight=60, category="Exams")]
        merge.apply(conn, items, "canvas_api", now)
        conn.execute("UPDATE items SET grade_points = 9, grade_max = 10 WHERE external_id = 'h1'")
        conn.execute("UPDATE items SET grade_points = 5, grade_max = 10 WHERE external_id = 'l1'")
        s = grades.summary(conn, "C")
        assert s["weights_sum_to"] == 100 and len(s["categories"]) == 3
        assert {c["kind"]: c["score_percent"] for c in s["categories"]} == {"Homework": 90.0, "Labs": 50.0, "Exams": None}
        assert s["current_percent"] == 70.0
