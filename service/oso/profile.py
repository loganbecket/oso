"""The learner profile: what the student has shown he knows, from his test results.

Every quiz Oso gives is recorded in detail. The quiz skill
calls `start_quiz` when it writes the questions, `record_answers` each time answers are graded (once,
or again after a hint or a retry), and `finish_quiz` after grading. A quiz that was handed out and never
answered stays recorded as abandoned.

Quizzes are taken in the quiz window (`quizwin.py`) rather than in the chat. The window times
each question, counts changed answers, grades multiple choice against the key Claude supplied (which is
never shown to the student), saves typed answers, and attaches written work (tablet pages or scans).
Claude then grades the rest from `grading_view`.

Checks of the student's own work are recorded too (`record_check`), and every course has a topic
list, seeded from its syllabus at setup (`set_topics`), that quizzes and checks tag against. A topic with
no results is "untested", so silence is never mistaken for mastery.

All numbers here are computed in plain Python; Claude supplies only the judgments it has to make while
writing and grading (each question's topic, theme, type, and difficulty; each answer's result and kind
of mistake).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime

from .config import Config

QUESTION_TYPES = ("multiple_choice", "short_answer", "worked_problem", "conceptual")
DIFFICULTIES = ("easy", "medium", "hard")
RESULTS = ("right", "partly_right", "wrong", "skipped")
MISTAKES = ("concept_gap", "calculation_slip", "misread_question", "incomplete")
CREDIT = {"right": 1.0, "partly_right": 0.5, "wrong": 0.0, "skipped": 0.0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS quizzes (
    id             INTEGER PRIMARY KEY,
    course         TEXT NOT NULL,
    topics         TEXT NOT NULL,          -- JSON list
    sources        TEXT NOT NULL,          -- JSON list of vault paths
    requested      TEXT,                   -- what the student asked for, e.g. "5 questions on kinematics"
    retake_of      INTEGER REFERENCES quizzes(id),
    handed_out_at  TEXT NOT NULL,
    submitted_at   TEXT,                   -- first answer received
    finished_at    TEXT,
    question_count INTEGER NOT NULL,
    score          REAL                    -- percent, set when finished
);
CREATE TABLE IF NOT EXISTS quiz_responses (
    question_id     INTEGER PRIMARY KEY REFERENCES quiz_questions(id),
    response        TEXT,                  -- the choice letter or typed answer; NULL if left blank
    seconds         REAL NOT NULL,         -- time the question was on screen
    changes         INTEGER NOT NULL,      -- times the answer changed after first being given
    first_answer_at TEXT                   -- when an answer was first given
);
CREATE TABLE IF NOT EXISTS course_topics (
    id         INTEGER PRIMARY KEY,
    course     TEXT NOT NULL,
    name       TEXT NOT NULL,
    key        TEXT NOT NULL,                -- normalized name used for matching
    week       INTEGER,                      -- week of the course it is taught, from the syllabus
    exams      TEXT NOT NULL DEFAULT '[]',   -- JSON list of exam names that cover it
    origin     TEXT NOT NULL,                -- 'syllabus' or 'added' (first seen in a quiz or check)
    created_at TEXT NOT NULL,
    UNIQUE (course, key)
);
CREATE TABLE IF NOT EXISTS checks (
    id            INTEGER PRIMARY KEY,
    course        TEXT NOT NULL,
    topic         TEXT NOT NULL,
    theme         TEXT,
    correct       INTEGER NOT NULL,          -- 1 if the attempt was right as submitted
    mistake       TEXT,                      -- kind of the first mistake, if any
    mistake_at    TEXT,                      -- where it went wrong, in a few words
    hints         INTEGER NOT NULL DEFAULT 0,
    full_solution INTEGER NOT NULL DEFAULT 0,
    checked_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_work (
    id       INTEGER PRIMARY KEY,
    quiz_id  INTEGER NOT NULL REFERENCES quizzes(id),
    page     TEXT NOT NULL,                -- vault path of one page image
    origin   TEXT NOT NULL,                -- 'tablet' or 'file'
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_questions (
    id          INTEGER PRIMARY KEY,
    quiz_id     INTEGER NOT NULL REFERENCES quizzes(id),
    number      INTEGER NOT NULL,
    topic       TEXT NOT NULL,
    theme       TEXT,
    qtype       TEXT NOT NULL,
    difficulty  TEXT NOT NULL,
    question    TEXT,
    source      TEXT,
    UNIQUE (quiz_id, number)
);
CREATE TABLE IF NOT EXISTS quiz_answers (
    question_id       INTEGER PRIMARY KEY REFERENCES quiz_questions(id),
    result            TEXT NOT NULL,
    mistake           TEXT,
    attempts          INTEGER NOT NULL,
    hint              INTEGER NOT NULL DEFAULT 0,
    first_answered_at TEXT NOT NULL,
    answered_at       TEXT NOT NULL
);
"""


class ProfileError(ValueError):
    """A plain-sentence problem with what a skill tried to record."""


COLUMNS = {
    "quizzes": {"mode": "TEXT NOT NULL DEFAULT 'chat'",
                "kind": "TEXT NOT NULL DEFAULT 'quiz'"},  # quiz, retake (the same questions again), or new_version
    "quiz_questions": {"choices": "TEXT", "answer_key": "TEXT",
                       "criteria": "TEXT",            # JSON: how Claude will grade it, fixed before he answers; never shown to him
                       "misconception_id": "INTEGER"},  # the open misconception this question is aimed at
    "quiz_answers": {"criterion": "TEXT",            # which grading criterion the answer met or missed
                     "note": "TEXT"},                # Claude's short feedback, shown when he reviews the quiz
}


def ensure(conn: sqlite3.Connection) -> None:
    from . import schema

    schema.apply(conn)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pick(value, allowed: tuple[str, ...], what: str) -> str:
    v = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v not in allowed:
        raise ProfileError(f"{what} must be one of {', '.join(allowed)}, not {value!r}.")
    return v


def start_quiz(conn: sqlite3.Connection, cfg: Config, course: str, questions: list[dict], requested: str | None = None,
               sources: list[str] | None = None, retake_of: int | None = None, now: str | None = None, kind: str = "quiz",
               window: bool = False) -> int:
    """Record a quiz as it is handed out. Each question: number, topic, theme, type, difficulty, the
    question text, and its source note; multiple choice also has `choices` (list) and `answer` (the key:
    a letter, or the exact choice text). Returns the quiz id."""
    ensure(conn)
    c = cfg.course_for(course)
    if c is None:
        raise ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    if not questions:
        raise ProfileError("A quiz needs at least one question.")
    if retake_of is not None and not conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (retake_of,)).fetchone():
        raise ProfileError(f"There is no earlier quiz {retake_of} to retake.")
    rows, numbers = [], set()
    when = now or _now()
    for i, q in enumerate(questions, start=1):
        n = int(q.get("number") or i)
        if n in numbers:
            raise ProfileError(f"Question {n} appears twice.")
        numbers.add(n)
        topic = str(q.get("topic") or "").strip()
        if not topic:
            raise ProfileError(f"Question {n} needs a topic.")
        topic = match_topic(conn, c.code, topic, when)
        qtype = _pick(q.get("type") or q.get("qtype"), QUESTION_TYPES, f"Question {n}'s type")
        choices, key = None, None
        if qtype == "multiple_choice":
            opts = _choice_texts(q.get("choices"))
            if window and len(opts) < 2:
                raise ProfileError(f"Question {n} is multiple choice and needs at least two choices.")
            if opts and all(re.fullmatch(r"[A-Za-z]", o) for o in opts):
                raise ProfileError(f"Question {n}'s choices are only letters; send the text of each choice.")
            if opts:
                key = _key_letter(q.get("answer"), opts, n) if (window or q.get("answer") is not None) else None
                choices = json.dumps(opts)
        if window and not str(q.get("question") or "").strip():
            raise ProfileError(f"Question {n} needs its text for the quiz window.")
        criteria = q.get("criteria")
        if window and not key and not criteria:
            raise ProfileError(f"Question {n} will be graded by Claude, so it needs its grading criteria now: the expected answer, "
                               "what earns full and partial credit, and the common wrong answers.")
        aimed = q.get("misconception")
        if aimed is not None and not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'misconceptions'").fetchone():
            aimed = None
        rows.append((n, topic, (str(q.get("theme")).strip() or None) if q.get("theme") else None,
                     qtype, _pick(q.get("difficulty"), DIFFICULTIES, f"Question {n}'s difficulty"),
                     q.get("question"), q.get("source"), choices, key,
                     json.dumps(criteria) if criteria else None, int(aimed) if aimed is not None else None))
    topics = list(dict.fromkeys(r[1] for r in rows))
    cur = conn.execute(
        """INSERT INTO quizzes (course, topics, sources, requested, retake_of, handed_out_at, question_count, mode, kind)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (c.code, json.dumps(topics), json.dumps(sources or []), requested, retake_of, when, len(rows),
         "window" if window else "chat", kind if kind in ("quiz", "new_version") else "quiz"),
    )
    quiz_id = cur.lastrowid
    conn.executemany(
        """INSERT INTO quiz_questions (quiz_id, number, topic, theme, qtype, difficulty, question, source, choices, answer_key,
                                       criteria, misconception_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(quiz_id, *r) for r in rows],
    )
    return quiz_id


# ---- topics ---------------------------------------------------------------------------------------


def topic_key(name: str) -> str:
    """Lowercase words without punctuation, filler words, or plural endings: "Newton's Laws" -> "newton law"."""
    words = re.findall(r"[a-z0-9]+", name.lower().replace("'s", ""))
    words = [w for w in words if w not in ("the", "a", "an", "of", "and", "to", "in")]
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def match_topic(conn: sqlite3.Connection, course: str, name: str, now: str | None = None) -> str:
    """The course's name for this topic. An exact match on the normalized name wins; otherwise the one
    topic whose words all appear in the other ("kinematics" and "1D kinematics"); otherwise it is added."""
    ensure(conn)
    key = topic_key(name)
    rows = conn.execute("SELECT name, key FROM course_topics WHERE LOWER(course) = LOWER(?)", (course,)).fetchall()
    for r in rows:
        if r["key"] == key:
            return r["name"]
    words = set(key.split())
    close = [r for r in rows if words and (set(r["key"].split()) <= words or words <= set(r["key"].split()))]
    if len(close) == 1:
        return close[0]["name"]
    conn.execute("INSERT INTO course_topics (course, name, key, origin, created_at) VALUES (?, ?, ?, 'added', ?)",
                 (course, name.strip(), key, now or _now()))
    return name.strip()


def set_topics(conn: sqlite3.Connection, cfg: Config, course: str, topics: list[dict], now: str | None = None) -> list[dict]:
    """Set a course's topics from its syllabus: [{name, week, exams: [...]}]. Topics added later by quizzes
    and checks are kept; a syllabus topic with the same normalized name takes over its record."""
    ensure(conn)
    c = cfg.course_for(course)
    if c is None:
        raise ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    when = now or _now()
    for t in topics:
        name = str(t.get("name") or "").strip()
        if not name:
            raise ProfileError("Every topic needs a name.")
        week = int(t["week"]) if t.get("week") not in (None, "") else None
        exams = json.dumps([str(e).strip() for e in (t.get("exams") or []) if str(e).strip()])
        conn.execute(
            """INSERT INTO course_topics (course, name, key, week, exams, origin, created_at) VALUES (?, ?, ?, ?, ?, 'syllabus', ?)
               ON CONFLICT(course, key) DO UPDATE SET name = excluded.name, week = excluded.week, exams = excluded.exams, origin = 'syllabus'""",
            (c.code, name, topic_key(name), week, exams, when),
        )
    return list_topics(conn, c.code)


def list_topics(conn: sqlite3.Connection, course: str) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        "SELECT name, week, exams, origin FROM course_topics WHERE LOWER(course) = LOWER(?) ORDER BY week IS NULL, week, id", (course,)
    ).fetchall()
    return [{"name": r["name"], "week": r["week"], "exams": json.loads(r["exams"]), "origin": r["origin"]} for r in rows]


# ---- checks of his own work ------------------------------------------------------------------------


def record_check(conn: sqlite3.Connection, cfg: Config, course: str, topic: str, correct: bool, theme: str | None = None,
                 mistake: str | None = None, mistake_at: str | None = None, hints: int = 0, full_solution: bool = False,
                 now: str | None = None) -> dict:
    """Record one check of the student's own attempt at a problem."""
    ensure(conn)
    c = cfg.course_for(course)
    if c is None:
        raise ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    if not str(topic or "").strip():
        raise ProfileError("A check needs a topic.")
    when = now or _now()
    kind = None if correct else _pick(mistake, MISTAKES, "The mistake")
    name = match_topic(conn, c.code, topic, when)
    cur = conn.execute(
        """INSERT INTO checks (course, topic, theme, correct, mistake, mistake_at, hints, full_solution, checked_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (c.code, name, (theme or "").strip() or None, 1 if correct else 0, kind, (mistake_at or "").strip() or None,
         max(0, int(hints or 0)), 1 if full_solution else 0, when),
    )
    return {"check_id": cur.lastrowid, "course": c.code, "topic": name}


def correct(conn: sqlite3.Connection, quiz_id: int | None = None, number: int | None = None, check_id: int | None = None,
            result: str | None = None, mistake: str | None = None, remove: bool = False, reason: str | None = None) -> str:
    """Fix a recorded result the student says is wrong: regrade one quiz question (the quiz's score is
    recomputed), or change or remove one check. Returns a plain sentence saying what changed."""
    ensure(conn)
    if check_id is not None:
        row = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
        if row is None:
            raise ProfileError(f"There is no check {check_id}.")
        if remove:
            conn.execute("DELETE FROM checks WHERE id = ?", (check_id,))
            return f"Removed check {check_id} ({row['topic']})."
        ok = _pick(result, ("right", "wrong"), "A check's result") == "right"
        kind = None if ok else _pick(mistake, MISTAKES, "The mistake")
        conn.execute("UPDATE checks SET correct = ?, mistake = ? WHERE id = ?", (1 if ok else 0, kind, check_id))
        return f"Check {check_id} ({row['topic']}) is now recorded as {'right' if ok else 'wrong'}."
    if quiz_id is None or number is None:
        raise ProfileError("Say which quiz and question, or which check, to correct.")
    q = conn.execute("SELECT id, topic FROM quiz_questions WHERE quiz_id = ? AND number = ?", (quiz_id, number)).fetchone()
    if q is None:
        raise ProfileError(f"Quiz {quiz_id} has no question {number}.")
    if remove:
        conn.execute("DELETE FROM quiz_answers WHERE question_id = ?", (q["id"],))
        verdict = "not graded"
    else:
        res = _pick(result, RESULTS, "The result")
        kind = _pick(mistake, MISTAKES, "The mistake") if res in ("partly_right", "wrong") else None
        old = conn.execute("SELECT result FROM quiz_answers WHERE question_id = ?", (q["id"],)).fetchone()
        if old is not None and old["result"] != res:
            # A changed grade needs its reason: the criterion that supports it, or the record being wrong.
            if not (reason or "").strip():
                raise ProfileError("Say why the grade changes: which grading criterion supports it, or what was recorded wrong.")
            from . import tutor

            tutor.ensure(conn)
            conn.execute("INSERT INTO regrades (question_id, old, new, reason, at) VALUES (?, ?, ?, ?, ?)",
                         (q["id"], old["result"], res, reason.strip(), _now()))
        if old is not None:
            conn.execute("UPDATE quiz_answers SET result = ?, mistake = ? WHERE question_id = ?", (res, kind, q["id"]))
        else:
            when = _now()
            conn.execute("INSERT INTO quiz_answers (question_id, result, mistake, attempts, hint, first_answered_at, answered_at) VALUES (?, ?, ?, 1, 0, ?, ?)",
                         (q["id"], res, kind, when, when))
        verdict = res.replace("_", " ")
    quiz = conn.execute("SELECT finished_at FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz["finished_at"]:
        conn.execute("UPDATE quizzes SET score = ? WHERE id = ?", (_progress(conn, quiz_id)["score"], quiz_id))
    return f"Quiz {quiz_id}, question {number} ({q['topic']}) is now {verdict}."


def retake(conn: sqlite3.Connection, cfg: Config, quiz_id: int, now: str | None = None) -> int:
    """The same questions again, blank, once. On a retake, right answers count for nothing toward where he stands
    (he has seen the answers); wrong ones count in full."""
    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    if quiz["kind"] == "retake":
        raise ProfileError("That is already a retake; each quiz can be retaken once.")
    if not quiz["submitted_at"]:
        raise ProfileError("That quiz hasn't been taken yet.")
    if conn.execute("SELECT 1 FROM quizzes WHERE retake_of = ? AND kind = 'retake'", (quiz_id,)).fetchone():
        raise ProfileError("That quiz has already been retaken once.")
    when = now or _now()
    cur = conn.execute(
        """INSERT INTO quizzes (course, topics, sources, requested, retake_of, handed_out_at, question_count, mode, kind)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'window', 'retake')""",
        (quiz["course"], quiz["topics"], quiz["sources"], f"retake of quiz {quiz_id}", quiz_id, when, quiz["question_count"]),
    )
    new_id = cur.lastrowid
    conn.execute(
        """INSERT INTO quiz_questions (quiz_id, number, topic, theme, qtype, difficulty, question, source, choices, answer_key,
                                       criteria, misconception_id)
           SELECT ?, number, topic, theme, qtype, difficulty, question, source, choices, answer_key, criteria, misconception_id
           FROM quiz_questions WHERE quiz_id = ?""",
        (new_id, quiz_id),
    )
    return int(new_id)


def delete_quiz(conn: sqlite3.Connection, cfg: Config, quiz_id: int) -> str:
    """Remove a quiz completely, as if it was never given: its questions, answers, window responses, and
    written-work pages. Retakes of it stay but no longer point to it. Topics that only this quiz had added
    (not from the syllabus, not used anywhere else) are removed too. Returns a plain sentence."""
    import shutil

    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    for r in conn.execute("SELECT id FROM quizzes WHERE retake_of = ? AND kind = 'retake'", (quiz_id,)).fetchall():
        delete_quiz(conn, cfg, r["id"])  # its retake goes with it
    qids = [r["id"] for r in conn.execute("SELECT id FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))]
    topics = {r["topic"] for r in conn.execute("SELECT topic FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))}
    for page in [r["page"] for r in conn.execute("SELECT page FROM quiz_work WHERE quiz_id = ?", (quiz_id,))]:
        (cfg.vault / page).unlink(missing_ok=True)
    from .quizwin import work_folder

    folder = work_folder(cfg, dict(quiz))
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    marks = ",".join("?" * len(qids))
    if qids:
        conn.execute(f"DELETE FROM quiz_answers WHERE question_id IN ({marks})", qids)
        conn.execute(f"DELETE FROM quiz_responses WHERE question_id IN ({marks})", qids)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'regrades'").fetchone():
            conn.execute(f"DELETE FROM regrades WHERE question_id IN ({marks})", qids)
    conn.execute("DELETE FROM quiz_work WHERE quiz_id = ?", (quiz_id,))
    conn.execute("DELETE FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
    conn.execute("UPDATE quizzes SET retake_of = NULL WHERE retake_of = ?", (quiz_id,))
    conn.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    for t in topics:
        used = conn.execute("SELECT 1 FROM quiz_questions q JOIN quizzes z ON z.id = q.quiz_id WHERE z.course = ? AND q.topic = ?",
                            (quiz["course"], t)).fetchone() or \
            conn.execute("SELECT 1 FROM checks WHERE course = ? AND topic = ?", (quiz["course"], t)).fetchone() or \
            _canvas_uses(conn, quiz["course"], t)
        if not used:
            conn.execute("DELETE FROM course_topics WHERE course = ? AND name = ? AND origin = 'added'", (quiz["course"], t))
    return f"Deleted quiz {quiz_id} and everything recorded with it."


def _canvas_uses(conn: sqlite3.Connection, course: str, topic: str) -> bool:
    try:
        return conn.execute(
            "SELECT 1 FROM canvas_assignment_topics t JOIN canvas_assignments a ON a.canvas_id = t.assignment_id WHERE a.course = ? AND t.topic = ?",
            (course, topic)).fetchone() is not None
    except sqlite3.OperationalError:
        return False  # Canvas never connected


def recent_checks(conn: sqlite3.Connection, course: str | None = None, limit: int = 20) -> list[dict]:
    ensure(conn)
    sql, params = "SELECT * FROM checks", []
    if course:
        sql += " WHERE LOWER(course) = LOWER(?)"
        params.append(course)
    sql += " ORDER BY checked_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


_LABEL = re.compile(r"^\(?([A-Za-z])[).:]\s+")


def _choice_texts(raw) -> list[str]:
    """The text of each choice, in order, however it was sent: a list of texts, a list labeled "A. text",
    a {"A": "text"} mapping, or a list of {"label", "text"} objects. Letters are added by the window."""
    if isinstance(raw, dict):
        items = [raw[k] for k in sorted(raw, key=str)]
    else:
        items = list(raw or [])
    out = []
    for c in items:
        if isinstance(c, dict):
            c = c.get("text") or c.get("choice") or c.get("value") or c.get("answer") or ""
        text = _LABEL.sub("", str(c).strip())
        if text:
            out.append(text)
    return out


def _key_letter(answer, opts: list[str], n: int) -> str:
    """The key as a letter (A, B, ...), given a letter or the exact text of the right choice."""
    a = str(answer or "").strip()
    letters = [chr(ord("A") + i) for i in range(len(opts))]
    if a.upper().rstrip(").") in letters:
        return a.upper().rstrip(").")
    for letter, opt in zip(letters, opts):
        if a.lower() == opt.lower():
            return letter
    raise ProfileError(f"Question {n}'s answer must be one of its choices (a letter like A, or the choice's text).")


def record_answers(conn: sqlite3.Connection, quiz_id: int, answers: list[dict], now: str | None = None,
                   auto: bool = False) -> dict:
    """Record graded answers. Each: number, result, and for anything not fully right the mistake kind;
    optionally hint (bool). Answering the same question again counts as another attempt. `auto` is the
    quiz window grading multiple choice, which cannot tell what kind of mistake a wrong pick was."""
    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    if quiz["finished_at"]:
        raise ProfileError(f"Quiz {quiz_id} is already finished; start a retake instead.")
    when = now or _now()
    for a in answers:
        n = int(a.get("number") or 0)
        q = conn.execute("SELECT id FROM quiz_questions WHERE quiz_id = ? AND number = ?", (quiz_id, n)).fetchone()
        if q is None:
            raise ProfileError(f"Quiz {quiz_id} has no question {n}.")
        result = _pick(a.get("result"), RESULTS, f"Question {n}'s result")
        mistake = None
        if result in ("partly_right", "wrong") and not (auto and not a.get("mistake")):
            mistake = _pick(a.get("mistake"), MISTAKES, f"Question {n}'s mistake")
        hint = 1 if a.get("hint") else 0
        criterion = (str(a.get("criterion")).strip() or None) if a.get("criterion") else None
        note = (str(a.get("note")).strip() or None) if a.get("note") else None
        prior = conn.execute("SELECT attempts, hint, first_answered_at FROM quiz_answers WHERE question_id = ?", (q["id"],)).fetchone()
        if prior is None:
            conn.execute(
                "INSERT INTO quiz_answers (question_id, result, mistake, attempts, hint, first_answered_at, answered_at, criterion, note) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)",
                (q["id"], result, mistake, hint, when, when, criterion, note),
            )
        else:
            conn.execute(
                "UPDATE quiz_answers SET result = ?, mistake = ?, attempts = ?, hint = ?, answered_at = ?, criterion = COALESCE(?, criterion), note = COALESCE(?, note) WHERE question_id = ?",
                (result, mistake, prior["attempts"] + 1, max(prior["hint"], hint), when, criterion, note, q["id"]),
            )
        aimed = conn.execute("SELECT misconception_id FROM quiz_questions WHERE id = ?", (q["id"],)).fetchone()["misconception_id"]
        if aimed and result == "right" and not hint and (prior is None):
            conn.execute("UPDATE misconceptions SET closed_at = ?, closed_by = ? WHERE id = ? AND closed_at IS NULL",
                         (when, f"right on quiz {quiz_id}, question {n}, aimed at it", aimed))
    if not quiz["submitted_at"]:
        conn.execute("UPDATE quizzes SET submitted_at = ? WHERE id = ?", (when, quiz_id))
    return _progress(conn, quiz_id)


def window_submit(conn: sqlite3.Connection, quiz_id: int, responses: dict[int, dict], now: str | None = None) -> dict:
    """Save what the student entered in the quiz window and grade the multiple choice against the key.
    responses: {number: {"response", "seconds", "changes", "first_answer_at"}}."""
    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    when = now or _now()
    graded = []
    for q in conn.execute("SELECT * FROM quiz_questions WHERE quiz_id = ? ORDER BY number", (quiz_id,)).fetchall():
        r = responses.get(q["number"]) or {}
        response = (str(r.get("response")).strip() or None) if r.get("response") is not None else None
        conn.execute(
            """INSERT INTO quiz_responses (question_id, response, seconds, changes, first_answer_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(question_id) DO UPDATE SET response = excluded.response, seconds = excluded.seconds,
                 changes = excluded.changes, first_answer_at = excluded.first_answer_at""",
            (q["id"], response, round(float(r.get("seconds") or 0), 1), int(r.get("changes") or 0), r.get("first_answer_at")),
        )
        if q["qtype"] == "multiple_choice" and q["answer_key"]:
            if response is None:
                graded.append({"number": q["number"], "result": "skipped"})
            else:
                graded.append({"number": q["number"], "result": "right" if response.upper() == q["answer_key"] else "wrong"})
    if graded:
        record_answers(conn, quiz_id, graded, now=when, auto=True)
    conn.execute("UPDATE quizzes SET submitted_at = ? WHERE id = ?", (when, quiz_id))
    return _progress(conn, quiz_id)


def add_work(conn: sqlite3.Connection, quiz_id: int, pages: list[str], origin: str, now: str | None = None) -> int:
    """Attach page images of written work (vault paths) to a quiz."""
    ensure(conn)
    if origin not in ("tablet", "file"):
        raise ProfileError("Written work comes from the tablet or a file.")
    conn.executemany("INSERT INTO quiz_work (quiz_id, page, origin, added_at) VALUES (?, ?, ?, ?)",
                     [(quiz_id, p, origin, now or _now()) for p in pages])
    return len(pages)


def grading_view(conn: sqlite3.Connection, cfg: Config, quiz_id: int) -> dict:
    """Everything Claude needs to grade a window quiz: each question with the student's response and
    timing, multiple choice already graded, and the pages of written work to match by their corner labels."""
    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    if not quiz["submitted_at"]:
        return {"quiz_id": quiz_id, "status": "handed_out", "note": "The student has not submitted this quiz yet."}
    rows = conn.execute(
        """SELECT q.number, q.topic, q.theme, q.qtype, q.question, q.choices, q.answer_key, q.criteria, q.misconception_id,
                  r.response, r.seconds, r.changes, a.result
           FROM quiz_questions q LEFT JOIN quiz_responses r ON r.question_id = q.id
           LEFT JOIN quiz_answers a ON a.question_id = q.id
           WHERE q.quiz_id = ? ORDER BY q.number""",
        (quiz_id,),
    ).fetchall()
    questions = []
    for r in rows:
        item = {"number": r["number"], "topic": r["topic"], "theme": r["theme"], "type": r["qtype"], "question": r["question"],
                "response": r["response"], "seconds": r["seconds"], "changes": r["changes"]}
        if r["criteria"]:
            item["criteria"] = json.loads(r["criteria"])
        if r["misconception_id"]:
            item["aimed_at_misconception"] = r["misconception_id"]
        if r["choices"]:
            item["choices"] = json.loads(r["choices"])
        if r["qtype"] == "multiple_choice" and r["answer_key"]:
            item["graded_by_window"] = r["result"]
            item["correct_choice"] = r["answer_key"]
        questions.append(item)
    work = [w["page"] for w in conn.execute("SELECT page FROM quiz_work WHERE quiz_id = ? ORDER BY id", (quiz_id,))]
    return {
        "quiz_id": quiz_id,
        "status": status(quiz),
        "minutes": minutes(quiz, conn),
        "questions": questions,
        "written_work": [{"path": p, "full_path": str(cfg.vault / p)} for p in work],
        "grading": _grading_rule(conn, quiz["course"]),
    }


def _grading_rule(conn: sqlite3.Connection, course: str) -> str:
    """How to grade."""
    return ("Grade each answer against its stored criteria only, and name the criterion it met or missed. A confident, "
            "long, or sympathetic answer earns nothing the criteria don't give it. Wrong is wrong; partly right only "
            "where the criteria give partial credit.")


def finish_quiz(conn: sqlite3.Connection, quiz_id: int, now: str | None = None) -> dict:
    """Close a quiz and store its score. Unanswered questions count as skipped."""
    ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise ProfileError(f"There is no quiz {quiz_id}.")
    p = _progress(conn, quiz_id)
    if not quiz["finished_at"]:
        conn.execute("UPDATE quizzes SET finished_at = ?, score = ? WHERE id = ?", (now or _now(), p["score"], quiz_id))
    return summary(conn, quiz_id)


def _progress(conn: sqlite3.Connection, quiz_id: int) -> dict:
    rows = conn.execute(
        """SELECT q.number, a.result FROM quiz_questions q LEFT JOIN quiz_answers a ON a.question_id = q.id
           WHERE q.quiz_id = ? ORDER BY q.number""",
        (quiz_id,),
    ).fetchall()
    credit = sum(CREDIT.get(r["result"] or "skipped", 0.0) for r in rows)
    return {
        "quiz_id": quiz_id,
        "answered": sum(1 for r in rows if r["result"]),
        "questions": len(rows),
        "score": round(100 * credit / len(rows), 1) if rows else 0.0,
    }


def summary(conn: sqlite3.Connection, quiz_id: int) -> dict:
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    rows = conn.execute(
        """SELECT q.number, q.topic, q.theme, q.qtype, q.difficulty, a.result, a.mistake, a.attempts, a.hint
           FROM quiz_questions q LEFT JOIN quiz_answers a ON a.question_id = q.id
           WHERE q.quiz_id = ? ORDER BY q.number""",
        (quiz_id,),
    ).fetchall()
    return {
        "quiz_id": quiz_id,
        "course": quiz["course"],
        "status": status(quiz),
        "score": quiz["score"] if quiz["finished_at"] else _progress(conn, quiz_id)["score"],
        "minutes": minutes(quiz, conn),
        "retake_of": quiz["retake_of"],
        "questions": [dict(r) for r in rows],
    }


def status(quiz) -> str:
    if quiz["finished_at"]:
        return "finished"
    return "in_progress" if quiz["submitted_at"] else "handed_out"


def minutes(quiz, conn: sqlite3.Connection | None = None) -> float | None:
    """Completion time in minutes. In the quiz window it is the measured time on the questions; in a chat
    it is handout to first answer, which includes any breaks."""
    if not quiz["submitted_at"]:
        return None
    if conn is not None and quiz["mode"] == "window":
        total = conn.execute(
            "SELECT SUM(r.seconds) FROM quiz_responses r JOIN quiz_questions q ON q.id = r.question_id WHERE q.quiz_id = ?",
            (quiz["id"],),
        ).fetchone()[0]
        if total is not None:
            return round(total / 60, 1)
    gap = datetime.fromisoformat(quiz["submitted_at"]) - datetime.fromisoformat(quiz["handed_out_at"])
    return round(gap.total_seconds() / 60, 1)


def recent_quizzes(conn: sqlite3.Connection, course: str | None = None, limit: int = 10) -> list[dict]:
    ensure(conn)
    sql, params = "SELECT * FROM quizzes", []
    if course:
        sql += " WHERE LOWER(course) = LOWER(?)"
        params.append(course)
    sql += " ORDER BY handed_out_at DESC, id DESC LIMIT ?"
    params.append(limit)
    out = []
    for q in conn.execute(sql, params).fetchall():
        out.append({
            "quiz_id": q["id"], "course": q["course"], "topics": json.loads(q["topics"]), "requested": q["requested"],
            "handed_out_at": q["handed_out_at"], "status": status(q), "score": q["score"], "minutes": minutes(q, conn),
            "questions": q["question_count"], "retake_of": q["retake_of"], "kind": q["kind"],
        })
    return out


def raw_dump(conn: sqlite3.Connection, limit: int = 10) -> str:
    """Plain text for `oso profile --raw`: recent quizzes with every question and answer."""
    lines = []
    for q in recent_quizzes(conn, limit=limit):
        s = summary(conn, q["quiz_id"])
        head = f"Quiz {q['quiz_id']} | {q['course']} | {q['handed_out_at']} | {s['status']}"
        head += f" | score {s['score']}%" if s["status"] == "finished" else ""
        head += f" | {s['minutes']} min" if s["minutes"] is not None else ""
        head += f" | retake of {q['retake_of']}" if q["retake_of"] else ""
        lines.append(head)
        if q["requested"]:
            lines.append(f"  asked for: {q['requested']}")
        for r in s["questions"]:
            theme = f" / {r['theme']}" if r["theme"] else ""
            ans = "not answered" if not r["result"] else (
                f"{r['result']}" + (f" ({r['mistake']})" if r["mistake"] else "") + f", {r['attempts']} attempt{'s' if r['attempts'] != 1 else ''}" + (", hint" if r["hint"] else ""))
            lines.append(f"  {r['number']}. {r['topic']}{theme} [{r['qtype']}, {r['difficulty']}]: {ans}")
        lines.append("")
    checks = recent_checks(conn, limit=limit)
    if checks:
        lines.append("Checks of his own work")
        for k in checks:
            theme = f" / {k['theme']}" if k["theme"] else ""
            res = "right" if k["correct"] else f"mistake: {k['mistake']}" + (f" ({k['mistake_at']})" if k["mistake_at"] else "")
            extra = (f", {k['hints']} hint{'s' if k['hints'] != 1 else ''}" if k["hints"] else "") + (", asked for the full solution" if k["full_solution"] else "")
            lines.append(f"  Check {k['id']} | {k['checked_at']} | {k['course']} | {k['topic']}{theme}: {res}{extra}")
        lines.append("")
    return "\n".join(lines) if lines else "Nothing recorded yet."
