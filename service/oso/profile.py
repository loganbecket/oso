"""The learner profile: what the student has shown he knows, from his test results.

Phase 1 of docs/learner-profile-plan.md: every quiz Oso gives is recorded in detail. The quiz skill
calls `start_quiz` when it shows the questions, `record_answers` each time the student answers (once,
or again after a hint or a retry), and `finish_quiz` after grading. A quiz that was handed out and never
answered stays recorded as abandoned.

All numbers here are computed in plain Python; Claude supplies only the judgments it has to make while
writing and grading (each question's topic, theme, type, and difficulty; each answer's result and kind
of mistake).
"""

from __future__ import annotations

import json
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


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pick(value, allowed: tuple[str, ...], what: str) -> str:
    v = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v not in allowed:
        raise ProfileError(f"{what} must be one of {', '.join(allowed)}, not {value!r}.")
    return v


def start_quiz(conn: sqlite3.Connection, cfg: Config, course: str, questions: list[dict], requested: str | None = None,
               sources: list[str] | None = None, retake_of: int | None = None, now: str | None = None) -> int:
    """Record a quiz as it is handed out. Each question: number, topic, theme, type, difficulty, and
    optionally the question text and its source note. Returns the quiz id."""
    ensure(conn)
    c = cfg.course_for(course)
    if c is None:
        raise ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    if not questions:
        raise ProfileError("A quiz needs at least one question.")
    if retake_of is not None and not conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (retake_of,)).fetchone():
        raise ProfileError(f"There is no earlier quiz {retake_of} to retake.")
    rows, numbers = [], set()
    for i, q in enumerate(questions, start=1):
        n = int(q.get("number") or i)
        if n in numbers:
            raise ProfileError(f"Question {n} appears twice.")
        numbers.add(n)
        topic = str(q.get("topic") or "").strip()
        if not topic:
            raise ProfileError(f"Question {n} needs a topic.")
        rows.append((n, topic, (str(q.get("theme")).strip() or None) if q.get("theme") else None,
                     _pick(q.get("type") or q.get("qtype"), QUESTION_TYPES, f"Question {n}'s type"),
                     _pick(q.get("difficulty"), DIFFICULTIES, f"Question {n}'s difficulty"),
                     q.get("question"), q.get("source")))
    topics = list(dict.fromkeys(r[1] for r in rows))
    cur = conn.execute(
        """INSERT INTO quizzes (course, topics, sources, requested, retake_of, handed_out_at, question_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (c.code, json.dumps(topics), json.dumps(sources or []), requested, retake_of, now or _now(), len(rows)),
    )
    quiz_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO quiz_questions (quiz_id, number, topic, theme, qtype, difficulty, question, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(quiz_id, *r) for r in rows],
    )
    return quiz_id


def record_answers(conn: sqlite3.Connection, quiz_id: int, answers: list[dict], now: str | None = None) -> dict:
    """Record graded answers. Each: number, result, and for anything not fully right the mistake kind;
    optionally hint (bool). Answering the same question again counts as another attempt."""
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
        if result in ("partly_right", "wrong"):
            mistake = _pick(a.get("mistake"), MISTAKES, f"Question {n}'s mistake")
        hint = 1 if a.get("hint") else 0
        prior = conn.execute("SELECT attempts, hint, first_answered_at FROM quiz_answers WHERE question_id = ?", (q["id"],)).fetchone()
        if prior is None:
            conn.execute(
                "INSERT INTO quiz_answers (question_id, result, mistake, attempts, hint, first_answered_at, answered_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
                (q["id"], result, mistake, hint, when, when),
            )
        else:
            conn.execute(
                "UPDATE quiz_answers SET result = ?, mistake = ?, attempts = ?, hint = ?, answered_at = ? WHERE question_id = ?",
                (result, mistake, prior["attempts"] + 1, max(prior["hint"], hint), when, q["id"]),
            )
    if not quiz["submitted_at"]:
        conn.execute("UPDATE quizzes SET submitted_at = ? WHERE id = ?", (when, quiz_id))
    return _progress(conn, quiz_id)


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
        "minutes": minutes(quiz),
        "retake_of": quiz["retake_of"],
        "questions": [dict(r) for r in rows],
    }


def status(quiz) -> str:
    if quiz["finished_at"]:
        return "finished"
    return "in_progress" if quiz["submitted_at"] else "handed_out"


def minutes(quiz) -> float | None:
    """Handout to first answer, in minutes. Includes any breaks: a chat has no stopwatch."""
    if not quiz["submitted_at"]:
        return None
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
            "handed_out_at": q["handed_out_at"], "status": status(q), "score": q["score"], "minutes": minutes(q),
            "questions": q["question_count"], "retake_of": q["retake_of"],
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
    return "\n".join(lines) if lines else "No quizzes recorded yet."
