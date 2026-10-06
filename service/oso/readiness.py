"""Readiness: is he ready for the exams coming up?

For each exam within `readiness_days` in a current course, the exam's topics (from the course's topic
list, which records which exams cover each topic) are checked against his results. A flag is raised
when any of these hold:

- no practice quiz on those topics yet
- some of those topics are still shaky or untested
- his last quiz on those topics scored below `quiz_warning_percent`
- his scores on those topics dropped across his last two quizzes on them
- his graded Canvas work on those topics averages below `quiz_warning_percent`, or some of it is missing

If no topic is mapped to the exam, the whole course's topics stand in, and the line says so.
The flags go into a "Readiness" section of `Today.md`, one line per exam.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from . import mastery, profile
from .config import Config

SLIP_POINTS = 10
SHOW_TOPICS = 3


def exam_topics(conn: sqlite3.Connection, course: str, exam_title: str) -> list[str]:
    """Topics on the course's list that name this exam (matched loosely: "Exam 1" fits "Midterm Exam 1 (Ch. 1-4)")."""
    want = set(profile.topic_key(exam_title).split())
    out = []
    for t in profile.list_topics(conn, course):
        for e in t["exams"]:
            words = set(profile.topic_key(e).split())
            if words and words <= want:
                out.append(t["name"])
                break
    return out


def _quizzes_on(conn: sqlite3.Connection, course: str, topics: list[str]) -> list[sqlite3.Row]:
    """Finished quizzes for the course with at least one question on these topics, oldest first."""
    if not topics:
        return []
    marks = ",".join("?" * len(topics))
    return conn.execute(
        f"""SELECT z.id, z.score, z.finished_at FROM quizzes z
            WHERE LOWER(z.course) = LOWER(?) AND z.finished_at IS NOT NULL
              AND EXISTS (SELECT 1 FROM quiz_questions q WHERE q.quiz_id = z.id AND q.topic IN ({marks}))
            ORDER BY z.finished_at, z.id""",
        (course, *topics),
    ).fetchall()


def _names(topics: list[str]) -> str:
    shown = ", ".join(topics[:SHOW_TOPICS])
    return shown + (f" and {len(topics) - SHOW_TOPICS} more" if len(topics) > SHOW_TOPICS else "")


def flags(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[dict]:
    from .today import _open_items  # the same open items Today.md lists

    profile.ensure(conn)
    out = []
    for item in _open_items(conn):
        if item["kind"] != "exam" or not item["due"] or not cfg.is_active(item["course_code"]):
            continue
        days = (item["due"].date() - now.date()).days
        c = cfg.course_for(item["course_code"])
        if days < 0 or days > cfg.readiness_days or c is None:
            continue
        topics = exam_topics(conn, c.code, item["title"])
        mapped = bool(topics)
        states = {t["topic"]: t for t in mastery.topic_states(conn, cfg, c.code, now)}
        if not topics:
            topics = list(states)
        reasons = []
        quizzes = _quizzes_on(conn, c.code, topics)
        if not quizzes:
            reasons.append("no practice quiz on its topics yet")
        shaky = [t for t in topics if states.get(t, {}).get("state") == "shaky"]
        untested = [t for t in topics if states.get(t, {}).get("state") == "untested"]
        if shaky:
            reasons.append(f"shaky: {_names(shaky)}")
        if untested and quizzes:  # with no quiz at all, "no practice quiz yet" already says it
            reasons.append(f"untested: {_names(untested)}")
        if quizzes and quizzes[-1]["score"] is not None and quizzes[-1]["score"] < cfg.quiz_warning_percent:
            reasons.append(f"last quiz {quizzes[-1]['score']:.0f}%")
        from . import canvas_store

        if mapped:  # graded Canvas work counts only where topics tie it to this exam
            avg, n = canvas_store.topic_average(conn, c.code, topics)
            if avg is not None and avg < cfg.quiz_warning_percent:
                reasons.append(f"graded work on its topics averages {avg:.0f}% ({n} assignment{'s' if n != 1 else ''})")
            gone = canvas_store.missing_on(conn, c.code, topics)
            if gone:
                reasons.append(f"missing: {_names(gone)}")
        if len(quizzes) >= 2 and None not in (quizzes[-1]["score"], quizzes[-2]["score"]) \
                and quizzes[-2]["score"] - quizzes[-1]["score"] >= SLIP_POINTS:
            reasons.append(f"scores dropping ({quizzes[-2]['score']:.0f}% then {quizzes[-1]['score']:.0f}%)")
        if reasons:
            out.append({"course": c.code, "name": c.name, "exam": item["title"], "due": item["due"], "days": days,
                        "mapped": mapped, "reasons": reasons})
    return sorted(out, key=lambda f: f["days"])


def section(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[str]:
    found = flags(conn, cfg, now)
    if not found:
        return []
    lines = ["## Readiness"]
    for f in found:
        when = "today" if f["days"] == 0 else "tomorrow" if f["days"] == 1 else f"{f['due'].strftime('%A')} ({f['days']} days)"
        why = "; ".join(f["reasons"])
        line = f"- **{f['name']}**: {f['exam']} {when}. {why[0].upper() + why[1:]}."
        if not f["mapped"]:
            line += " (The syllabus doesn't say which topics this exam covers, so this uses the whole course.)"
        lines.append(line)
    lines.append("")
    return lines
