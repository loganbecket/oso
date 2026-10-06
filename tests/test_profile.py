import sqlite3
from pathlib import Path

import pytest

from oso import profile
from oso.config import Config, Course


@pytest.fixture
def env(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    yield conn, cfg
    conn.close()


QUESTIONS = [
    {"number": 1, "topic": "Kinematics", "theme": "projectile motion", "type": "worked problem", "difficulty": "medium", "question": "A ball...", "source": "Courses/2026 Fall/Physics/Notes/w2.md"},
    {"number": 2, "topic": "Kinematics", "theme": "free fall", "type": "multiple_choice", "difficulty": "easy"},
    {"number": 3, "topic": "Forces", "type": "conceptual", "difficulty": "hard"},
    {"number": 4, "topic": "Forces", "theme": "friction", "type": "short_answer", "difficulty": "medium"},
]


def test_full_quiz_recorded(env):
    conn, cfg = env
    qid = profile.start_quiz(conn, cfg, "phys-110", QUESTIONS, requested="4 questions on kinematics and forces",
                             sources=["Courses/2026 Fall/Physics/Notes/w2.md"], now="2026-10-06T14:00:00+00:00")
    p = profile.record_answers(conn, qid, [
        {"number": 1, "result": "right"},
        {"number": 2, "result": "wrong", "mistake": "concept gap"},
        {"number": 3, "result": "partly right", "mistake": "incomplete", "hint": True},
    ], now="2026-10-06T14:12:30+00:00")
    assert p == {"quiz_id": qid, "answered": 3, "questions": 4, "score": 37.5}
    # a second try at question 2, after the method was shown
    profile.record_answers(conn, qid, [{"number": 2, "result": "right"}], now="2026-10-06T14:15:00+00:00")
    s = profile.finish_quiz(conn, qid, now="2026-10-06T14:16:00+00:00")
    assert s["status"] == "finished" and s["score"] == 62.5 and s["minutes"] == 12.5 and s["course"] == "PHYS-110"
    q = {r["number"]: r for r in s["questions"]}
    assert q[2]["attempts"] == 2 and q[2]["result"] == "right" and q[2]["mistake"] is None
    assert q[3]["hint"] == 1 and q[3]["mistake"] == "incomplete"
    assert q[4]["result"] is None  # never answered: counted as skipped in the score
    assert q[1]["qtype"] == "worked_problem"
    with pytest.raises(profile.ProfileError, match="already finished"):
        profile.record_answers(conn, qid, [{"number": 4, "result": "right"}])
    dump = profile.raw_dump(conn)
    assert "score 62.5%" in dump and "12.5 min" in dump and "2. Kinematics / free fall [multiple_choice, easy]: right, 2 attempts" in dump
    assert "4. Forces / friction [short_answer, medium]: not answered" in dump


def test_retake_and_abandoned(env):
    conn, cfg = env
    first = profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[:2], now="2026-10-06T10:00:00+00:00")
    profile.finish_quiz(conn, first)
    retake = profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[:2], retake_of=first, now="2026-10-07T10:00:00+00:00")
    abandoned = profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[2:], now="2026-10-08T10:00:00+00:00")
    recent = profile.recent_quizzes(conn, "PHYS-110")
    assert [r["quiz_id"] for r in recent] == [abandoned, retake, first]
    assert recent[0]["status"] == "handed_out" and recent[0]["minutes"] is None and recent[0]["topics"] == ["Forces"]
    assert recent[1]["retake_of"] == first
    assert recent[2]["score"] == 0.0
    with pytest.raises(profile.ProfileError, match="no earlier quiz 999"):
        profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[:1], retake_of=999)


def test_plain_errors(env):
    conn, cfg = env
    with pytest.raises(profile.ProfileError, match="no course"):
        profile.start_quiz(conn, cfg, "CHEM-1", QUESTIONS)
    with pytest.raises(profile.ProfileError, match="type must be one of"):
        profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "x", "type": "essay", "difficulty": "easy"}])
    with pytest.raises(profile.ProfileError, match="needs a topic"):
        profile.start_quiz(conn, cfg, "PHYS-110", [{"type": "conceptual", "difficulty": "easy"}])
    qid = profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[:1])
    with pytest.raises(profile.ProfileError, match="mistake must be one of"):
        profile.record_answers(conn, qid, [{"number": 1, "result": "wrong"}])
    with pytest.raises(profile.ProfileError, match="no question 7"):
        profile.record_answers(conn, qid, [{"number": 7, "result": "right"}])
