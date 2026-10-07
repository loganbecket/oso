"""A study partner that knows him: conversation notes, trajectories, misconceptions, honest verdicts, grading
criteria, second grading, the honesty flags, where study time goes, and how he learns."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from oso import mastery, merge, profile, tutor
from oso.config import Config, Course
from oso.db import SCHEMA, Item

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
C = "MATH-150"


@pytest.fixture
def env(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cfg = Config(vault=tmp_path / "vault", courses=[Course(C, "Calculus", "2026 Fall/Calculus"), Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    profile.set_topics(conn, cfg, C, [{"name": "Integrals"}, {"name": "Limits"}])
    profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Forces"}])
    yield conn, cfg
    conn.close()


def at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def quiz(conn, cfg, topic, results, days_ago, difficulty="medium", course=C, confidence=None, misconception=None):
    qs = [{"number": i + 1, "topic": topic, "type": "short_answer", "difficulty": difficulty, "misconception": misconception}
          for i in range(len(results))]
    qid = profile.start_quiz(conn, cfg, course, qs, now=at(days_ago))
    if confidence:
        profile.window_submit(conn, qid, {i + 1: {"response": "x", "seconds": 5, "changes": 0, "confidence": confidence}
                                          for i in range(len(results))}, now=at(days_ago))
    profile.record_answers(conn, qid, [{"number": i + 1, "result": r, "mistake": None if r == "right" else "concept_gap"}
                                       for i, r in enumerate(results)], now=at(days_ago))
    profile.finish_quiz(conn, qid, now=at(days_ago))
    return qid


def stage(conn, cfg, topic="Integrals", now=NOW, course=C):
    return {t["topic"]: t for t in tutor.topics(conn, cfg, course, now, record=True)}[topic]


def test_notes_match_topics_fold_repeats_and_keep_misconceptions_open(env):
    conn, cfg = env
    a = tutor.note_signal(conn, cfg, "confused", C, "integral", "I don't get why we need an integral here", now=at(1))
    assert a["topic"] == "Integrals"
    b = tutor.note_signal(conn, cfg, "confused", C, "Integrals", "still lost", now=at(0.98))
    assert b["note"] == a["note"] and conn.execute("SELECT times FROM signals").fetchone()["times"] == 2
    m = tutor.note_signal(conn, cfg, "misconception", C, "Integrals", belief="thinks an integral is needed whenever a rate is given", now=at(1))
    again = tutor.note_signal(conn, cfg, "misconception", C, "Integrals", belief="Thinks the integral is needed whenever a rate is given.", now=at(0.5))
    assert again["misconception"] == m["misconception"]
    assert [x["belief"] for x in tutor.open_misconceptions(conn, C)] == ["thinks an integral is needed whenever a rate is given"]
    tutor.note_signal(conn, cfg, "goal", C, words="at least a B+", target=87)
    tutor.note_signal(conn, cfg, "preference", words="worked examples help me more than definitions")
    assert tutor.goal(conn, C)["target"] == 87 and tutor.preferences(conn)[0]["preference"].startswith("worked examples")
    with pytest.raises(tutor.TutorError, match="kind must be one of"):
        tutor.note_signal(conn, cfg, "bored", C, "Integrals")
    with pytest.raises(tutor.TutorError, match="needs the course and the topic"):
        tutor.note_signal(conn, cfg, "confused", C)


def test_the_integral_example_end_to_end(env):
    conn, cfg = env
    assert stage(conn, cfg)["stage"] == "untested"
    tutor.note_signal(conn, cfg, "confused", C, "Integrals", "I'm really confused about why we need an integral here", now=at(40))
    s = stage(conn, cfg, now=NOW - timedelta(days=40))
    assert s["stage"] == "needs_focus" and s["next_step"].startswith("explain it")
    tutor.note_signal(conn, cfg, "explained", C, "Integrals", "worked example: area under a velocity graph", now=at(39.9))
    assert stage(conn, cfg, now=NOW - timedelta(days=39))["stage"] == "explained"
    quiz(conn, cfg, "Integrals", ["right", "right", "right"], 38)
    assert stage(conn, cfg, now=NOW - timedelta(days=38))["stage"] == "practicing"  # three results aren't enough
    quiz(conn, cfg, "Integrals", ["right", "right", "right"], 36)
    s = stage(conn, cfg, now=NOW - timedelta(days=36))
    assert s["stage"] == "practicing" and "own words" in s["next_step"]  # the numbers alone don't make it solid
    tutor.note_signal(conn, cfg, "explained_well", C, "Integrals", "you integrate a rate to get the total change", now=at(35))
    s = stage(conn, cfg, now=NOW - timedelta(days=35))
    assert s["stage"] == "solid" and s["became_solid"] and s["status"].startswith("Integrals: 5 of 5 right")
    assert stage(conn, cfg, now=NOW - timedelta(days=13))["stage"] == "maintaining"  # solid for three weeks
    s = stage(conn, cfg, now=NOW)
    assert s["stage"] == "maintaining" and s["next_step"].startswith("due for review")  # left alone for weeks
    tutor.note_signal(conn, cfg, "confused", C, "Integrals", "wait, why is there a +C", now=at(0))
    s = stage(conn, cfg, now=NOW)
    assert s["stage"] == "needs_focus" and "confused" in s["status"]
    assert "confused" in s["trail"] and "quiz 1" in s["trail"]


def test_conversation_alone_never_makes_a_topic_solid(env):
    conn, cfg = env
    for d in range(6):
        tutor.note_signal(conn, cfg, "explained_well", C, "Limits", f"explanation {d}", now=at(d * 3))
        tutor.note_signal(conn, cfg, "solved", C, "Limits", now=at(d * 3 + 1))
    assert stage(conn, cfg, "Limits")["stage"] == "practicing"


def test_easy_questions_alone_never_make_a_topic_solid(env):
    conn, cfg = env
    quiz(conn, cfg, "Limits", ["right"] * 8, 2, difficulty="easy")
    tutor.note_signal(conn, cfg, "explained_well", C, "Limits", now=at(1))
    s = stage(conn, cfg, "Limits")
    assert s["stage"] == "practicing" and "medium or hard" in s["next_step"]


def test_misconceptions_close_only_on_evidence(env):
    conn, cfg = env
    m = tutor.note_signal(conn, cfg, "misconception", C, "Integrals", belief="integral whenever a rate is given", now=at(5))["misconception"]
    assert stage(conn, cfg)["stage"] == "needs_focus"
    quiz(conn, cfg, "Integrals", ["wrong"], 4, misconception=m)
    assert tutor.open_misconceptions(conn, C)  # a wrong answer on it keeps it open
    quiz(conn, cfg, "Integrals", ["right"], 3, misconception=m)
    assert not tutor.open_misconceptions(conn, C)
    closed = conn.execute("SELECT closed_by FROM misconceptions").fetchone()["closed_by"]
    assert "aimed at it" in closed
    m2 = tutor.note_signal(conn, cfg, "misconception", C, "Limits", belief="a limit is the function's value there", now=at(2))["misconception"]
    tutor.note_signal(conn, cfg, "explained_well", C, "Limits", "the value it approaches, not where it is", misconception_id=m2, now=at(1))
    assert not tutor.open_misconceptions(conn, C)
    assert "Reopened" in tutor.forget(conn, misconception=m2, reopen=True)
    assert len(tutor.open_misconceptions(conn, C)) == 1


def test_sure_but_wrong_moves_a_topic_to_focus_and_guessing_counts_less(env):
    conn, cfg = env
    quiz(conn, cfg, "Forces", ["right"] * 6, 3, course="PHYS-110")
    tutor.note_signal(conn, cfg, "explained_well", "PHYS-110", "Forces", now=at(2.5))
    assert stage(conn, cfg, "Forces", course="PHYS-110")["stage"] == "solid"
    quiz(conn, cfg, "Forces", ["wrong", "wrong", "right"], 1, course="PHYS-110", confidence="sure")
    s = stage(conn, cfg, "Forces", course="PHYS-110")
    assert s["stage"] == "needs_focus" and "sure but wrong" in s["status"]
    flags = tutor.course_flags(conn, cfg, "PHYS-110", now=NOW)
    assert flags["overconfident"]["line"].startswith("Sure on 3 answers this week and 2 were wrong, mostly on Forces")
    quiz(conn, cfg, "Limits", ["right"], 1, confidence="guessing")
    assert [e["credit"] for e in mastery.evidence(conn, C) if e["topic"] == "Limits"] == [0.5]


def test_practice_too_easy_flag_appears_at_the_threshold_and_clears(env):
    conn, cfg = env

    def ev(practice, real):
        out = [{"topic": "Forces", "credit": c, "source": "quiz 1", "test": True, "at": at(5)} for c in practice]
        for i, credit in enumerate(real):
            out.append({"topic": "Forces", "credit": credit, "source": f"canvas {i}", "test": True, "at": at(4)})
        return out

    flags = tutor.course_flags(conn, cfg, "PHYS-110", ev([1, 1, 1, 1, 0.9], [0.7, 0.75]), NOW)
    assert flags["practice_too_easy"]["points"] >= 15 and "practice is too easy" in flags["practice_too_easy"]["line"]
    assert "practice_too_easy" not in tutor.course_flags(conn, cfg, "PHYS-110", ev([1, 1, 1, 1, 0.9], [0.7]), NOW)  # one assessment isn't a pattern
    assert "practice_too_easy" not in tutor.course_flags(conn, cfg, "PHYS-110", ev([0.9, 0.8], [0.85, 0.8]), NOW)  # lined up again


def test_hard_labels_checked_against_results(env):
    conn, cfg = env
    quiz(conn, cfg, "Limits", ["right"] * 6, 2, difficulty="hard")
    assert "hard_too_easy" in tutor.course_flags(conn, cfg, C, now=NOW)


def test_criteria_are_fixed_before_he_answers_and_come_back_for_grading(env):
    conn, cfg = env
    q = {"number": 1, "topic": "Limits", "type": "short_answer", "difficulty": "medium", "question": "lim x->0 sin x / x?"}
    with pytest.raises(profile.ProfileError, match="grading criteria"):
        profile.start_quiz(conn, cfg, C, [q], window=True)
    criteria = {"expected": "1", "full_credit": "1, with a reason", "partial_credit": "1 with no reason", "wrong_answers": {"0": "plugged in 0"}}
    qid = profile.start_quiz(conn, cfg, C, [{**q, "criteria": criteria}], window=True)
    profile.window_submit(conn, qid, {1: {"response": "1", "seconds": 30, "changes": 0, "confidence": "think_so"}})
    view = profile.grading_view(conn, cfg, qid)
    assert view["questions"][0]["criteria"] == criteria and "stored criteria" in view["grading"]
    profile.record_answers(conn, qid, [{"number": 1, "result": "partly_right", "mistake": "incomplete", "criterion": "partial: no reason given"}])
    assert conn.execute("SELECT criterion FROM quiz_answers").fetchone()["criterion"] == "partial: no reason given"


def test_second_grader_blind_and_its_grade_counts(env):
    conn, cfg = env
    ids = [quiz(conn, cfg, "Limits", ["right", "wrong"], 10 - i) for i in range(5)]
    assert not tutor.needs_second_grade(conn, ids[3]) and tutor.needs_second_grade(conn, ids[4])  # every fifth
    high = quiz(conn, cfg, "Limits", ["right", "right"], 4)
    assert tutor.needs_second_grade(conn, high)  # and any Claude-graded quiz at 90% or more
    blind = tutor.blind_view(conn, cfg, ids[4])
    assert all("result" not in q and "graded_by_window" not in q for q in blind["questions"])
    for qid in ids[:4]:
        tutor.record_second_grade(conn, qid, [{"number": 1, "result": "wrong", "mistake": "concept_gap"}, {"number": 2, "result": "wrong"}])
    out = tutor.record_second_grade(conn, ids[4], [{"number": 1, "result": "partly_right", "mistake": "incomplete"}, {"number": 2, "result": "wrong"}])
    assert out["changed"] == [1] and out["score"] == 25.0
    gen = tutor.generosity(conn, C)
    assert gen["first_more_generous"] == 5 and "more generous than the second grader" in gen["line"]
    assert "more generous" in profile.grading_view(conn, cfg, quiz(conn, cfg, "Limits", ["right"], 0))["grading"]


def test_where_study_time_goes(env):
    conn, cfg = env
    merge.apply(conn, [Item(source="syllabus", external_id="m1", course_code=C, title="Midterm", kind="exam",
                            due_at=datetime.now(UTC) + timedelta(days=2))], "syllabus", datetime.now(UTC))
    tutor.note_signal(conn, cfg, "confused", C, "Integrals", "lost")
    tutor.note_signal(conn, cfg, "goal", C, words="an A", target=93)
    ranked = tutor.attention(conn, cfg)
    assert ranked[0]["course"] == C and ranked[0]["share_percent"] > 50
    assert any("exam in 2 days" in r for r in ranked[0]["reasons"]) and any("need focus" in r for r in ranked[0]["reasons"])


def test_how_i_learn_note_and_corrections(env):
    conn, cfg = env
    p = tutor.note_signal(conn, cfg, "preference", words="worked examples help me more than definitions", now=at(3))
    tutor.note_signal(conn, cfg, "explained", C, "Limits", "analogy: walking toward a door", now=at(2))
    tutor.note_signal(conn, cfg, "explained_well", C, "Limits", now=at(1.9))
    tutor.note_signal(conn, cfg, "explained", C, "Integrals", "formal definition", now=at(1.5))
    tutor.note_signal(conn, cfg, "confused", C, "Integrals", "still lost", now=at(1.4))
    path = tutor.write_how_i_learn(conn, cfg, NOW)
    text = path.read_text()
    assert "worked examples help me more than definitions" in text
    assert "analogy: walking toward a door: understood the first time" in text and "formal definition: needed another try" in text
    tutor.forget(conn, note=p["note"])
    assert "worked examples" not in tutor.write_how_i_learn(conn, cfg, NOW).read_text()


def test_the_standing_rule_is_in_every_study_command_and_the_vault_instructions():
    skills = Path(__file__).parent.parent / "service" / "oso" / "skills"
    for name in ("oso-explain", "oso-quiz", "oso-check", "oso-study-guide", "oso-flashcards", "oso-summarize", "oso-check-notes",
                 "oso-profile", "oso-plan"):
        text = (skills / f"{name}.md").read_text()
        assert "Be a direct, honest tutor." in text and "note_signal" in text, name
    from oso import instructions

    assert "Be a direct, honest tutor." in instructions.TEMPLATE and "note_signal" in instructions.TEMPLATE
