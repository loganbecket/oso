import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import habits, merge, profile
from oso.config import Config, Course
from oso.db import SCHEMA, Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 30, 9, 0, tzinfo=TZ)


@pytest.fixture
def env(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics"),
                                                    Course("ENGL-1301", "Composition", "2026 Fall/Composition")])
    profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Kinematics", "exams": ["Exam 1"]}, {"name": "Forces", "exams": ["Exam 1"]}])
    profile.set_topics(conn, cfg, "ENGL-1301", [{"name": "Thesis"}])
    yield conn, cfg
    conn.close()


def quiz(conn, cfg, course, results_by_topic, at, window_seconds=None):
    when = at.isoformat(timespec="seconds")
    qs, ans, n = [], [], 0
    for topic, results in results_by_topic.items():
        for r in results:
            n += 1
            qs.append({"number": n, "topic": topic, "type": "short_answer", "difficulty": "medium", "question": "?", "criteria": "x"})
            ans.append({"number": n, "result": r, "mistake": None if r == "right" else "concept_gap"})
    qid = profile.start_quiz(conn, cfg, course, qs, now=when, window=window_seconds is not None)
    if window_seconds is not None:
        profile.window_submit(conn, qid, {i + 1: {"response": "x", "seconds": window_seconds, "changes": 0} for i in range(n)}, now=when)
    profile.record_answers(conn, qid, ans, now=when)
    profile.finish_quiz(conn, qid, now=when)
    return qid


def test_not_enough_data_at_first(env):
    conn, cfg = env
    quiz(conn, cfg, "PHYS-110", {"Kinematics": ["right"] * 3}, NOW - timedelta(days=2))
    h = habits.compute(conn, cfg, NOW)
    assert not h["enough_data"] and h["results"] == 3


def test_metrics(env):
    conn, cfg = env
    exam_day = NOW - timedelta(days=10)
    merge.apply(conn, [Item(source="syllabus", external_id="e1", course_code="PHYS-110", title="Exam 1", kind="exam", due_at=exam_day)], "syllabus", NOW)
    merge.apply(conn, [Item(source="syllabus2", external_id="p1", course_code="ENGL-1301", title="Essay 2", kind="assignment",
                            due_at=NOW + timedelta(days=9), weight=20)], "syllabus2", NOW)
    start = NOW - timedelta(days=30)
    quiz(conn, cfg, "PHYS-110", {"Kinematics": ["right", "wrong"], "Forces": ["wrong"]}, start, window_seconds=90)        # 33%
    quiz(conn, cfg, "PHYS-110", {"Kinematics": ["right", "right"]}, start + timedelta(days=3), window_seconds=60)        # retest within a week, better
    quiz(conn, cfg, "PHYS-110", {"Kinematics": ["right"] * 4}, exam_day - timedelta(days=1), window_seconds=40)
    quiz(conn, cfg, "PHYS-110", {"Kinematics": ["right"] * 4, "Forces": ["right"] * 2}, NOW - timedelta(days=3), window_seconds=30)
    profile.record_check(conn, cfg, "ENGL-1301", "Thesis", correct=False, mistake="incomplete", now=(NOW - timedelta(days=2)).isoformat())

    h = habits.compute(conn, cfg, NOW)
    assert h["enough_data"] and h["days_of_records"] == 28
    assert h["lead_time"] == [{"course": "Physics", "exam": "Exam 1", "date": exam_day.date().isoformat(), "days_ahead": 20}]
    assert h["follow_through"] == {"missed": 3, "retested_within_week": 1, "retest_improved": 1}
    [t] = h["trend"]
    assert t["course"] == "Physics" and t["first_three_weeks"] == round((100 / 3 + 100 + 100) / 3, 1) and t["last_three_weeks"] == 100.0
    alloc = {a["course"]: a for a in h["allocation"]}
    assert alloc["Physics"]["share_percent"] == 92 and alloc["Composition"]["share_percent"] == 8
    assert alloc["Composition"]["weight_due_next_4_weeks"] == 20
    assert h["pace"] == {"window_quizzes": 4, "first_seconds_per_question": 75, "recent_seconds_per_question": 35}

    md = habits.numbers_markdown(h)
    assert "Physics Exam 1" in md and "20 days ahead" in md and "Topics missed: 3; tested again within a week: 1; better on the retest: 1." in md
    path = habits.save(cfg, "Your first practice quiz for Exam 1 came 20 days ahead.", h, NOW)
    text = (cfg.vault / path).read_text()
    assert path == "Oso/Profile/Habits.md" and text.index("20 days ahead.") < text.index("## The numbers")
