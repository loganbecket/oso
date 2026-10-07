import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from oso import mastery, profile
from oso.config import Config, Course

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics", term="2026 Fall")])
    profile.set_topics(conn, cfg, "PHYS-110", [
        {"name": "Kinematics", "week": 2, "exams": ["Exam 1"]},
        {"name": "Forces", "week": 4, "exams": ["Exam 1"]},
        {"name": "Energy", "week": 7, "exams": ["Final"]},
    ])
    yield conn, cfg
    conn.close()


def quiz(conn, cfg, topic, results, days_ago, hint=False):
    when = (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")
    qs = [{"number": i + 1, "topic": topic, "type": "short_answer", "difficulty": "medium"} for i in range(len(results))]
    qid = profile.start_quiz(conn, cfg, "PHYS-110", qs, now=when)
    profile.record_answers(conn, qid, [
        {"number": i + 1, "result": r, "mistake": None if r == "right" else "concept_gap", "hint": hint} for i, r in enumerate(results)
    ], now=when)
    profile.finish_quiz(conn, qid, now=when)
    return qid


def states(conn, cfg):
    return {t["topic"]: t for t in mastery.topic_states(conn, cfg, "PHYS-110", NOW)}


def test_untested_shaky_strong(env):
    conn, cfg = env
    assert {n: t["state"] for n, t in states(conn, cfg).items()} == {"Kinematics": "untested", "Forces": "untested", "Energy": "untested"}
    quiz(conn, cfg, "Kinematics", ["right", "right"], 3)
    assert states(conn, cfg)["Kinematics"]["state"] == "untested"  # two results are not enough
    quiz(conn, cfg, "Kinematics", ["right", "right", "right", "right"], 2)
    assert states(conn, cfg)["Kinematics"]["state"] == "shaky"  # results alone aren't enough: he hasn't explained it
    from oso import tutor

    tutor.note_signal(conn, cfg, "explained_well", "PHYS-110", "Kinematics", "it's the rate of change of velocity",
                      now=(NOW - timedelta(days=2)).isoformat())
    k = states(conn, cfg)["Kinematics"]
    assert k["state"] == "strong" and k["accuracy"] == 100.0 and k["results"] == 6 and k["last_practiced"] == "2026-10-30"
    quiz(conn, cfg, "Forces", ["wrong", "right", "partly_right"], 1)
    f = states(conn, cfg)["Forces"]
    assert f["state"] == "shaky" and f["accuracy"] == 50.0 and f["common_mistake"] == "concept_gap"


def test_help_caps_credit_and_checks_count(env):
    conn, cfg = env
    quiz(conn, cfg, "Energy", ["right", "right", "right"], 1, hint=True)
    assert states(conn, cfg)["Energy"]["accuracy"] == 50.0
    profile.record_check(conn, cfg, "PHYS-110", "Energy", correct=True, now=(NOW - timedelta(days=1)).isoformat())
    e = states(conn, cfg)["Energy"]
    assert e["results"] == 4 and e["accuracy"] == 62.5 and "check 1" in e["sources"]


def test_old_results_fade_and_trend(env):
    conn, cfg = env
    quiz(conn, cfg, "Forces", ["right"] * 5, 90)   # long ago: strong then
    quiz(conn, cfg, "Forces", ["wrong"] * 5, 1)    # now: slipping
    f = states(conn, cfg)["Forces"]
    assert f["trend"] == "slipping" and f["accuracy"] < 10 and f["state"] == "shaky"
    quiz(conn, cfg, "Kinematics", ["wrong"] * 5, 10)
    quiz(conn, cfg, "Kinematics", ["right"] * 5, 1)
    assert states(conn, cfg)["Kinematics"]["trend"] == "improving"


def test_profile_file_written_and_not_churned(env):
    conn, cfg = env
    quiz(conn, cfg, "Forces", ["wrong", "right", "right"], 1)
    [path] = mastery.write_all(conn, cfg, NOW)
    assert path.name == "Physics (2026 Fall).md"
    text = path.read_text()
    assert "## Practicing\n- **Forces**: 2 of 3 right in the last 3 results (2026-10-31 to 2026-10-31); practicing; mostly concept gaps; on Exam 1. Next: practice." in text
    assert "  - Trail: quiz 1 2026-10-31, 2 of 3" in text
    assert "## Not yet tested\n- **Kinematics**: no results yet; untested; on Exam 1. Next: a few questions to find out." in text
    mtime = path.stat().st_mtime_ns
    mastery.write_all(conn, cfg, NOW + timedelta(minutes=15))
    assert path.stat().st_mtime_ns == mtime  # unchanged content is not rewritten every check
    p = mastery.course_profile(conn, cfg, "phys-110", NOW)
    assert [t["topic"] for t in p["shaky"]] == ["Forces"] and len(p["untested"]) == 2
