import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import merge, profile, readiness, today
from oso.config import Config, Course
from oso.db import SCHEMA, Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)  # a Monday


@pytest.fixture
def env(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    profile.set_topics(conn, cfg, "PHYS-110", [
        {"name": "Kinematics", "exams": ["Exam 2"]},
        {"name": "Forces", "exams": ["Exam 2"]},
        {"name": "Energy", "exams": ["Final"]},
    ])
    yield conn, cfg
    conn.close()


def exam(conn, title, days):
    merge.apply(conn, [Item(source="syllabus", external_id=title, course_code="PHYS-110", title=title, kind="exam",
                            due_at=NOW + timedelta(days=days))], "syllabus", NOW)


def quiz(conn, cfg, results_by_topic, days_ago):
    when = (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")
    qs, answers, n = [], [], 0
    for topic, results in results_by_topic.items():
        for r in results:
            n += 1
            qs.append({"number": n, "topic": topic, "type": "short_answer", "difficulty": "medium"})
            answers.append({"number": n, "result": r, "mistake": None if r == "right" else "concept_gap"})
    qid = profile.start_quiz(conn, cfg, "PHYS-110", qs, now=when)
    profile.record_answers(conn, qid, answers, now=when)
    profile.finish_quiz(conn, qid, now=when)


def reasons(conn, cfg):
    return {f["exam"]: f["reasons"] for f in readiness.flags(conn, cfg, NOW)}


def test_no_practice_yet(env):
    conn, cfg = env
    exam(conn, "Midterm Exam 2 (chapters 3-5)", 4)
    assert reasons(conn, cfg) == {"Midterm Exam 2 (chapters 3-5)": ["no practice quiz on its topics yet"]}
    assert readiness.exam_topics(conn, "PHYS-110", "Midterm Exam 2 (chapters 3-5)") == ["Kinematics", "Forces"]


def test_far_off_and_finished_exams_are_quiet(env):
    conn, cfg = env
    exam(conn, "Final", 20)
    assert reasons(conn, cfg) == {}


def test_shaky_untested_and_low_last_quiz(env):
    conn, cfg = env
    exam(conn, "Exam 2", 3)
    quiz(conn, cfg, {"Forces": ["wrong", "right", "wrong"]}, 2)
    assert reasons(conn, cfg) == {"Exam 2": ["shaky: Forces", "untested: Kinematics", "last quiz 33%"]}
    text = today.render(conn, cfg, NOW)
    assert "## Readiness\n- **Physics**: Exam 2 Thursday (3 days). Shaky: Forces; untested: Kinematics; last quiz 33%." in text
    assert text.index("## Due today") < text.index("## Readiness") < text.index("## Due this week")


def test_ready_means_no_line(env):
    conn, cfg = env
    exam(conn, "Exam 2", 5)
    quiz(conn, cfg, {"Kinematics": ["right"] * 6, "Forces": ["right"] * 6}, 2)
    from oso import tutor

    for t in ("Kinematics", "Forces"):
        tutor.note_signal(conn, cfg, "explained_well", "PHYS-110", t, now=(NOW - timedelta(days=1)).isoformat())
    assert reasons(conn, cfg) == {}
    assert "## Readiness" not in today.render(conn, cfg, NOW)


def test_dropping_scores(env):
    conn, cfg = env
    exam(conn, "Exam 2", 6)
    quiz(conn, cfg, {"Kinematics": ["right"] * 6, "Forces": ["right"] * 6}, 6)
    quiz(conn, cfg, {"Kinematics": ["right"] * 4, "Forces": ["right", "right", "right", "wrong"]}, 1)
    from oso import tutor

    tutor.note_signal(conn, cfg, "explained_well", "PHYS-110", "Kinematics", now=(NOW - timedelta(days=1)).isoformat())
    r = reasons(conn, cfg)["Exam 2"]
    assert r[-1] == "scores dropping (100% then 88%)"
    assert r[0].startswith("shaky: Forces")  # 90% is not strong


def test_unmapped_exam_uses_whole_course(env):
    conn, cfg = env
    exam(conn, "Quiz day", 2)
    [f] = readiness.flags(conn, cfg, NOW)
    assert not f["mapped"]
    assert "uses the whole course" in "\n".join(readiness.section(conn, cfg, NOW))


def test_finished_course_is_skipped(env):
    conn, cfg = env
    exam(conn, "Exam 2", 3)
    cfg.courses[0].finished = True
    assert reasons(conn, cfg) == {}
