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


WINDOW_QS = [
    {"number": 1, "topic": "Kinematics", "type": "multiple_choice", "difficulty": "easy", "question": "Units of acceleration?",
     "choices": ["m/s", "m/s^2", "N"], "answer": "B"},
    {"number": 2, "topic": "Kinematics", "type": "multiple_choice", "difficulty": "easy", "question": "g on Earth?",
     "choices": ["9.8 m/s^2", "1 m/s^2"], "answer": "9.8 m/s^2"},
    {"number": 3, "topic": "Forces", "type": "short_answer", "difficulty": "medium", "question": "State Newton's second law."},
    {"number": 4, "topic": "Forces", "type": "worked_problem", "difficulty": "hard", "question": "A 2 kg block..."},
]


def test_window_quiz_grades_choices_and_hands_the_rest_to_claude(env, tmp_path: Path):
    from oso import quizwin

    conn, cfg = env
    qid = profile.start_quiz(conn, cfg, "PHYS-110", WINDOW_QS, window=True, now="2026-10-06T14:00:00+00:00")
    quiz, qs = quizwin.load_questions(conn, qid)
    assert qs[1]["choices"] == ["9.8 m/s^2", "1 m/s^2"] and "answer" not in qs[0]  # the window never gets the key

    t = [0.0]
    s = quizwin.QuizSession(qs, clock=lambda: t[0], wall=lambda: "2026-10-06T14:00:30+00:00")
    t[0] = 30; s.answer("A"); s.answer("B")          # changed once
    t[0] = 40; s.go(1); t[0] = 55; s.answer("B")      # wrong
    t[0] = 60; s.go(2); t[0] = 120; s.answer("F = ma")
    t[0] = 130; s.go(0); t[0] = 135                   # went back to look
    assert s.unanswered() == [4]
    responses = s.responses()
    assert responses[1]["seconds"] == 45 and responses[1]["changes"] == 1 and responses[2]["seconds"] == 20 and responses[3]["seconds"] == 70
    assert responses[3]["response"] == "F = ma" and responses[4]["response"] is None

    p = profile.window_submit(conn, qid, responses, now="2026-10-06T14:02:20+00:00")
    assert p["answered"] == 2 and p["score"] == 25.0  # only the multiple choice is graded so far

    pdf = tmp_path / "scan.pdf"
    from PIL import Image
    Image.new("L", (600, 800), 255).save(pdf, save_all=True, append_images=[Image.new("L", (600, 800), 255)])
    photo = tmp_path / "q4.jpg"
    Image.new("RGB", (400, 300), "white").save(photo)
    assert quizwin.import_work(conn, cfg, quiz, [pdf, photo], "file") == 3
    view = profile.grading_view(conn, cfg, qid)
    assert view["minutes"] == round(135 / 60, 1)
    q = {x["number"]: x for x in view["questions"]}
    assert q[1]["graded_by_window"] == "right" and q[2]["graded_by_window"] == "wrong" and q[2]["correct_choice"] == "A"
    assert q[3]["response"] == "F = ma" and "graded_by_window" not in q[3]
    pages = [w["path"] for w in view["written_work"]]
    assert pages == [f"Courses/2026 Fall/Physics/Quizzes/Quiz {qid}/pages/page 0{i}.{ext}" for i, ext in ((1, "png"), (2, "png"), (3, "jpg"))]
    assert all((cfg.vault / p).exists() for p in pages)

    profile.record_answers(conn, qid, [{"number": 3, "result": "right"}, {"number": 4, "result": "partly_right", "mistake": "calculation_slip"}])
    s2 = profile.finish_quiz(conn, qid)
    assert s2["score"] == 62.5 and s2["minutes"] == round(135 / 60, 1)


def test_window_quiz_needs_text_and_valid_keys(env):
    conn, cfg = env
    with pytest.raises(profile.ProfileError, match="needs its text"):
        profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "x", "type": "short_answer", "difficulty": "easy"}], window=True)
    with pytest.raises(profile.ProfileError, match="at least two choices"):
        profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "x", "type": "multiple_choice", "difficulty": "easy", "question": "?", "choices": ["a"], "answer": "A"}], window=True)
    with pytest.raises(profile.ProfileError, match="must be one of its choices"):
        profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "x", "type": "multiple_choice", "difficulty": "easy", "question": "?", "choices": ["a", "b"], "answer": "D"}], window=True)
    view = profile.grading_view(conn, cfg, profile.start_quiz(conn, cfg, "PHYS-110", WINDOW_QS[2:3], window=True))
    assert view["status"] == "handed_out"


def test_topics_from_syllabus_and_matching(env):
    conn, cfg = env
    out = profile.set_topics(conn, cfg, "PHYS-110", [
        {"name": "Kinematics", "week": 2, "exams": ["Exam 1"]},
        {"name": "Newton's Laws", "week": 4, "exams": ["Exam 1", "Final"]},
        {"name": "Work and Energy", "week": 7},
    ])
    assert [t["name"] for t in out] == ["Kinematics", "Newton's Laws", "Work and Energy"]
    assert out[1]["exams"] == ["Exam 1", "Final"] and out[2]["exams"] == []
    assert profile.match_topic(conn, "PHYS-110", "newton laws") == "Newton's Laws"
    assert profile.match_topic(conn, "PHYS-110", "1D kinematics") == "Kinematics"
    assert profile.match_topic(conn, "PHYS-110", "energy") == "Work and Energy"
    assert profile.match_topic(conn, "PHYS-110", "Momentum") == "Momentum"  # new: added
    assert [t["origin"] for t in profile.list_topics(conn, "PHYS-110")][-1] == "added"
    # quizzes use the course's names
    qid = profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "kinematics", "type": "conceptual", "difficulty": "easy"}])
    assert profile.summary(conn, qid)["questions"][0]["topic"] == "Kinematics"
    # a syllabus re-run takes over an added topic and keeps the rest
    profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Momentum", "week": 9, "exams": ["Final"]}])
    t = {x["name"]: x for x in profile.list_topics(conn, "PHYS-110")}
    assert t["Momentum"]["origin"] == "syllabus" and t["Momentum"]["week"] == 9 and "Kinematics" in t


def test_checks_recorded(env):
    conn, cfg = env
    profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Kinematics", "week": 2}])
    a = profile.record_check(conn, cfg, "PHYS-110", "kinematics", correct=False, theme="projectile motion",
                             mistake="calculation slip", mistake_at="dropped the sign on g", hints=2, now="2026-10-06T15:00:00+00:00")
    assert a["topic"] == "Kinematics"
    profile.record_check(conn, cfg, "PHYS-110", "Kinematics", correct=True, now="2026-10-06T16:00:00+00:00")
    checks = profile.recent_checks(conn, "PHYS-110")
    assert [c["correct"] for c in checks] == [1, 0]
    assert checks[1]["mistake"] == "calculation_slip" and checks[1]["hints"] == 2 and checks[1]["mistake_at"] == "dropped the sign on g"
    assert "Kinematics / projectile motion: mistake: calculation_slip (dropped the sign on g), 2 hints" in profile.raw_dump(conn)
    with pytest.raises(profile.ProfileError, match="mistake must be one of"):
        profile.record_check(conn, cfg, "PHYS-110", "Kinematics", correct=False)
    with pytest.raises(profile.ProfileError, match="no course"):
        profile.record_check(conn, cfg, "BIO", "x", correct=True)


def test_corrections(env):
    conn, cfg = env
    qid = profile.start_quiz(conn, cfg, "PHYS-110", QUESTIONS[:2])
    profile.record_answers(conn, qid, [{"number": 1, "result": "wrong", "mistake": "concept_gap"}, {"number": 2, "result": "right"}])
    assert profile.finish_quiz(conn, qid)["score"] == 50.0
    assert "is now right" in profile.correct(conn, quiz_id=qid, number=1, result="right")
    assert profile.summary(conn, qid)["score"] == 100.0 and profile.summary(conn, qid)["questions"][0]["mistake"] is None
    assert "not graded" in profile.correct(conn, quiz_id=qid, number=2, remove=True)
    assert profile.summary(conn, qid)["score"] == 50.0
    c = profile.record_check(conn, cfg, "PHYS-110", "Forces", correct=True)
    assert "now recorded as wrong" in profile.correct(conn, check_id=c["check_id"], result="wrong", mistake="misread question")
    assert profile.recent_checks(conn)[0]["mistake"] == "misread_question"
    assert "Removed check" in profile.correct(conn, check_id=c["check_id"], remove=True)
    assert profile.recent_checks(conn) == []
    with pytest.raises(profile.ProfileError, match="Say which"):
        profile.correct(conn, result="right")


def test_delete_quiz_removes_everything(env, tmp_path: Path):
    from PIL import Image

    from oso import mastery, quizwin

    conn, cfg = env
    profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Kinematics"}])
    keep = profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "Kinematics", "type": "conceptual", "difficulty": "easy"}])
    profile.record_answers(conn, keep, [{"number": 1, "result": "right"}])
    trial = profile.start_quiz(conn, cfg, "PHYS-110", [
        {"number": 1, "topic": "Kinematics", "type": "multiple_choice", "difficulty": "easy", "question": "?", "choices": ["a", "b"], "answer": "A"},
        {"number": 2, "topic": "Dummy topic", "type": "worked_problem", "difficulty": "easy", "question": "Solve"},
    ], window=True)
    profile.window_submit(conn, trial, {1: {"response": "B", "seconds": 5, "changes": 0}, 2: {"response": None, "seconds": 9, "changes": 0}})
    photo = tmp_path / "w.png"
    Image.new("RGB", (100, 100), "white").save(photo)
    quiz, _ = quizwin.load_questions(conn, trial)
    quizwin.import_work(conn, cfg, quiz, [photo], "file")
    folder = quizwin.work_folder(cfg, quiz)
    assert folder.exists()
    retake = profile.start_quiz(conn, cfg, "PHYS-110", [{"topic": "Kinematics", "type": "conceptual", "difficulty": "easy"}], retake_of=trial)

    assert "Deleted quiz" in profile.delete_quiz(conn, cfg, trial)
    assert not folder.exists()
    assert [q["quiz_id"] for q in profile.recent_quizzes(conn)] == [retake, keep]
    assert profile.recent_quizzes(conn)[0]["retake_of"] is None
    for table in ("quiz_answers", "quiz_responses", "quiz_work"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE rowid IN (SELECT rowid FROM {table})").fetchone()[0] == (1 if table == "quiz_answers" else 0)
    assert [t["name"] for t in profile.list_topics(conn, "PHYS-110")] == ["Kinematics"]  # the trial's made-up topic is gone
    assert mastery.topic_states(conn, cfg, "PHYS-110")[0]["results"] == 1
    with pytest.raises(profile.ProfileError, match="no quiz"):
        profile.delete_quiz(conn, cfg, trial)
