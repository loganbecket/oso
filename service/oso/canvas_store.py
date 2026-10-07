"""What Oso has read from Canvas, kept in its database.

Each check replaces the stored picture with what Canvas shows now: courses with current grades,
assignment groups and weights, assignments, his submissions (score, late, missing, excused), and
instructor comments, and, for Canvas quizzes whose results the instructor lets students see, how he did on
each question of his latest attempt. The raw Canvas record is kept with each row so a new question can be answered
without reading Canvas again. Newly graded work and new comments become events that Today.md lists.

Claude reads it through `canvas_info`, and tags each new assignment with the syllabus topics it covers
(`tag_assignments`). Tagged, graded assignments are evidence in the learner profile, and readiness
uses graded and missing work on an exam's topics.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from . import profile
from .config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS canvas_courses (
    canvas_id     INTEGER PRIMARY KEY,
    code          TEXT NOT NULL,
    name          TEXT,
    current_score REAL,
    current_grade TEXT,
    raw           TEXT NOT NULL,
    read_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canvas_assignments (
    canvas_id   INTEGER PRIMARY KEY,
    course      TEXT NOT NULL,
    name        TEXT NOT NULL,
    due_at      TEXT,
    points      REAL,
    group_name  TEXT,
    group_weight REAL,
    is_quiz     INTEGER NOT NULL DEFAULT 0,
    url         TEXT,
    raw         TEXT NOT NULL,
    read_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canvas_submissions (
    assignment_id INTEGER PRIMARY KEY,
    course        TEXT NOT NULL,
    score         REAL,
    grade         TEXT,
    submitted_at  TEXT,
    graded_at     TEXT,
    late          INTEGER NOT NULL DEFAULT 0,
    missing       INTEGER NOT NULL DEFAULT 0,
    excused       INTEGER NOT NULL DEFAULT 0,
    raw           TEXT NOT NULL,
    read_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canvas_comments (
    canvas_id     INTEGER PRIMARY KEY,
    assignment_id INTEGER NOT NULL,
    author        TEXT,
    comment       TEXT NOT NULL,
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS canvas_quiz_questions (
    assignment_id INTEGER NOT NULL,
    question_id   INTEGER NOT NULL,
    attempt       INTEGER NOT NULL,      -- the attempt these results are from (his latest graded one)
    attempts      INTEGER NOT NULL,      -- how many attempts he has made
    result        TEXT NOT NULL,         -- right, partly_right, wrong
    points        REAL,
    PRIMARY KEY (assignment_id, question_id)
);
CREATE TABLE IF NOT EXISTS canvas_assignment_topics (
    assignment_id INTEGER NOT NULL,
    topic         TEXT NOT NULL,
    PRIMARY KEY (assignment_id, topic)
);
CREATE TABLE IF NOT EXISTS canvas_tagged (
    assignment_id INTEGER PRIMARY KEY,      -- tagged (possibly with no topics: "doesn't fit any")
    tagged_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canvas_events (
    id     INTEGER PRIMARY KEY,
    at     TEXT NOT NULL,
    course TEXT NOT NULL,
    text   TEXT NOT NULL
);
"""


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fmt_score(score: float | None, points: float | None) -> str:
    if score is None:
        return "graded"
    s = f"{score:g}"
    return f"{s}/{points:g}" if points else s


def save(conn: sqlite3.Connection, api, now: str | None = None) -> dict[str, int]:
    """Store what the last fetch read. Returns counts, including new grades and comments."""
    ensure(conn)
    when = now or _now()
    codes = {}
    for c in api.courses:
        code = c.get("course_code") or str(c["id"])
        codes[c["id"]] = code
        enr = next((e for e in c.get("enrollments") or [] if isinstance(e, dict) and e.get("type") in ("student", "StudentEnrollment")), {})
        conn.execute(
            """INSERT INTO canvas_courses (canvas_id, code, name, current_score, current_grade, raw, read_at) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(canvas_id) DO UPDATE SET code = excluded.code, name = excluded.name, current_score = excluded.current_score,
                 current_grade = excluded.current_grade, raw = excluded.raw, read_at = excluded.read_at""",
            (c["id"], code, c.get("name"), enr.get("computed_current_score"), enr.get("computed_current_grade"), json.dumps(c), when),
        )
    points = {}
    names = {}
    for a in api.assignments:
        g = api.groups.get(str(a.get("assignment_group_id"))) or {}
        points[a["id"]] = a.get("points_possible")
        names[a["id"]] = (a["_course_code"], (a.get("name") or "Untitled assignment").strip())
        is_quiz = 1 if a.get("is_quiz_assignment") or "online_quiz" in (a.get("submission_types") or []) or a.get("quiz_id") else 0
        raw = {k: v for k, v in a.items() if k != "submission"}
        conn.execute(
            """INSERT INTO canvas_assignments (canvas_id, course, name, due_at, points, group_name, group_weight, is_quiz, url, raw, read_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(canvas_id) DO UPDATE SET course = excluded.course, name = excluded.name, due_at = excluded.due_at,
                 points = excluded.points, group_name = excluded.group_name, group_weight = excluded.group_weight,
                 is_quiz = excluded.is_quiz, url = excluded.url, raw = excluded.raw, read_at = excluded.read_at""",
            (a["id"], a["_course_code"], names[a["id"]][1], a.get("due_at"), a.get("points_possible"), g.get("name"),
             g.get("group_weight"), is_quiz, a.get("html_url"), json.dumps(raw), when),
        )
    subs = {s["assignment_id"]: s for s in api.submissions if s.get("assignment_id") is not None}
    for a in api.assignments:  # assignments carry a submission too; the submissions list wins when present
        if a["id"] not in subs and isinstance(a.get("submission"), dict):
            subs[a["id"]] = {**a["submission"], "assignment_id": a["id"], "_course_code": a["_course_code"]}
    counts = {"courses": len(api.courses), "assignments": len(api.assignments), "submissions": 0, "new_grades": 0, "new_comments": 0}
    for aid, s in subs.items():
        if aid not in names:
            continue
        course, title = names[aid]
        prev = conn.execute("SELECT score, graded_at FROM canvas_submissions WHERE assignment_id = ?", (aid,)).fetchone()
        score = s.get("score")
        graded = s.get("graded_at") if score is not None or s.get("grade") else None
        conn.execute(
            """INSERT INTO canvas_submissions (assignment_id, course, score, grade, submitted_at, graded_at, late, missing, excused, raw, read_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(assignment_id) DO UPDATE SET course = excluded.course, score = excluded.score, grade = excluded.grade,
                 submitted_at = excluded.submitted_at, graded_at = excluded.graded_at, late = excluded.late, missing = excluded.missing,
                 excused = excluded.excused, raw = excluded.raw, read_at = excluded.read_at""",
            (aid, course, score, s.get("grade"), s.get("submitted_at"), graded, 1 if s.get("late") else 0,
             1 if s.get("missing") else 0, 1 if s.get("excused") else 0,
             json.dumps({k: v for k, v in s.items() if k != "submission_comments"}), when),
        )
        counts["submissions"] += 1
        if graded and (prev is None or prev["graded_at"] != graded or prev["score"] != score):
            conn.execute("INSERT INTO canvas_events (at, course, text) VALUES (?, ?, ?)",
                         (when, course, f"{title} graded: {_fmt_score(score, points.get(aid))}"))
            counts["new_grades"] += 1
        counts["quiz_questions"] = counts.get("quiz_questions", 0) + _save_quiz_questions(conn, aid, s)
        for cm in s.get("submission_comments") or []:
            if not isinstance(cm, dict) or cm.get("id") is None:
                continue
            if conn.execute("SELECT 1 FROM canvas_comments WHERE canvas_id = ?", (cm["id"],)).fetchone():
                continue
            conn.execute("INSERT INTO canvas_comments (canvas_id, assignment_id, author, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                         (cm["id"], aid, cm.get("author_name"), cm.get("comment") or "", cm.get("created_at")))
            conn.execute("INSERT INTO canvas_events (at, course, text) VALUES (?, ?, ?)",
                         (when, course, f"New comment on {title}" + (f" from {cm['author_name']}" if cm.get("author_name") else "")))
            counts["new_comments"] += 1
    return counts


def _save_quiz_questions(conn: sqlite3.Connection, aid: int, s: dict) -> int:
    """Per-question results from a quiz submission's history, when Canvas shows them to the student."""
    tries = [h for h in s.get("submission_history") or [] if isinstance(h, dict) and isinstance(h.get("submission_data"), list)]
    if not tries:
        return 0
    latest = max(tries, key=lambda h: (h.get("attempt") or 0, h.get("graded_at") or ""))
    rows = []
    for q in latest["submission_data"]:
        if not isinstance(q, dict) or q.get("question_id") is None or "correct" not in q:
            continue
        c = q["correct"]
        result = "right" if c is True else "partly_right" if c in ("partial", "partially_correct") else "wrong"
        rows.append((aid, int(q["question_id"]), int(latest.get("attempt") or 1), len(tries), result, q.get("points")))
    if rows:
        conn.execute("DELETE FROM canvas_quiz_questions WHERE assignment_id = ?", (aid,))
        conn.executemany(
            "INSERT INTO canvas_quiz_questions (assignment_id, question_id, attempt, attempts, result, points) VALUES (?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def quiz_questions(conn: sqlite3.Connection, aid: int) -> dict | None:
    rows = conn.execute("SELECT result, attempt, attempts FROM canvas_quiz_questions WHERE assignment_id = ?", (aid,)).fetchall()
    if not rows:
        return None
    return {"questions": len(rows), "right": sum(1 for r in rows if r["result"] == "right"),
            "partly_right": sum(1 for r in rows if r["result"] == "partly_right"),
            "wrong": sum(1 for r in rows if r["result"] == "wrong"), "attempt": rows[0]["attempt"], "attempts": rows[0]["attempts"]}


# ---- reading it back ----------------------------------------------------------------------------------


def recent_events(conn: sqlite3.Connection, now: datetime, hours: int = 24) -> list[sqlite3.Row]:
    ensure(conn)
    since = (now - timedelta(hours=hours)).astimezone(UTC).isoformat(timespec="seconds")
    return conn.execute("SELECT at, course, text FROM canvas_events WHERE at >= ? ORDER BY at", (since,)).fetchall()


def missing_work(conn: sqlite3.Connection, cfg: Config) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        """SELECT a.canvas_id, a.course, a.name, a.due_at, a.url FROM canvas_submissions s JOIN canvas_assignments a ON a.canvas_id = s.assignment_id
           WHERE s.missing = 1 AND s.excused = 0 ORDER BY a.due_at"""
    ).fetchall()
    return [dict(r) for r in rows if cfg.is_active(r["course"])]


def info(conn: sqlite3.Connection, cfg: Config, course: str, what: str = "summary") -> dict:
    """What Claude asks for: summary (grade, recent scores, missing and late work), assignments (every
    assignment with its score), comments (instructor feedback), or untagged (graded work awaiting topics)."""
    ensure(conn)
    c = cfg.course_for(course)
    code = c.code if c else course
    crs = conn.execute("SELECT * FROM canvas_courses WHERE LOWER(code) = LOWER(?)", (code,)).fetchone()
    base = conn.execute(
        """SELECT a.canvas_id, a.name, a.due_at, a.points, a.group_name, a.group_weight, a.is_quiz, a.url,
                  s.score, s.grade, s.submitted_at, s.graded_at, s.late, s.missing, s.excused
           FROM canvas_assignments a LEFT JOIN canvas_submissions s ON s.assignment_id = a.canvas_id
           WHERE LOWER(a.course) = LOWER(?) ORDER BY a.due_at""",
        (code,),
    ).fetchall()
    rows = [dict(r) for r in base]
    if what == "assignments":
        tags = _tags(conn)
        out = []
        for r in rows:
            item = {**r, "topics": tags.get(r["canvas_id"], [])}
            q = quiz_questions(conn, r["canvas_id"])
            if q:
                item["quiz_questions"] = q
            out.append(item)
        return {"course": code, "assignments": out}
    if what == "comments":
        cms = conn.execute(
            """SELECT a.name AS assignment, m.author, m.comment, m.created_at FROM canvas_comments m
               JOIN canvas_assignments a ON a.canvas_id = m.assignment_id WHERE LOWER(a.course) = LOWER(?) ORDER BY m.created_at DESC""",
            (code,),
        ).fetchall()
        return {"course": code, "comments": [dict(r) for r in cms]}
    if what == "untagged":
        tagged = {r[0] for r in conn.execute("SELECT assignment_id FROM canvas_tagged")}
        return {"course": code, "topics": [t["name"] for t in profile.list_topics(conn, code)],
                "untagged": [{"canvas_id": r["canvas_id"], "name": r["name"], "group": r["group_name"], "due_at": r["due_at"]}
                             for r in rows if r["canvas_id"] not in tagged]}
    graded = [r for r in rows if r["score"] is not None]
    return {
        "course": code,
        "current_score": crs["current_score"] if crs else None,
        "current_grade": crs["current_grade"] if crs else None,
        "recent_scores": [{"name": r["name"], "score": r["score"], "points": r["points"], "graded_at": r["graded_at"]}
                          for r in sorted(graded, key=lambda r: r["graded_at"] or "", reverse=True)[:10]],
        "missing": [r["name"] for r in rows if r["missing"] and not r["excused"]],
        "late": [r["name"] for r in rows if r["late"]],
        "read_at": crs["read_at"] if crs else None,
    }


def _tags(conn: sqlite3.Connection) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for r in conn.execute("SELECT assignment_id, topic FROM canvas_assignment_topics ORDER BY topic"):
        out.setdefault(r["assignment_id"], []).append(r["topic"])
    return out


def tag(conn: sqlite3.Connection, cfg: Config, tags: list[dict], now: str | None = None) -> int:
    """Store topics for assignments: [{canvas_id, topics: [...]}]. An empty list means it fits no topic."""
    ensure(conn)
    when = now or _now()
    n = 0
    for t in tags:
        aid = int(t["canvas_id"])
        a = conn.execute("SELECT course FROM canvas_assignments WHERE canvas_id = ?", (aid,)).fetchone()
        if a is None:
            raise profile.ProfileError(f"There is no Canvas assignment {aid}.")
        conn.execute("DELETE FROM canvas_assignment_topics WHERE assignment_id = ?", (aid,))
        for name in t.get("topics") or []:
            topic = profile.match_topic(conn, a["course"], str(name), when)
            conn.execute("INSERT OR IGNORE INTO canvas_assignment_topics (assignment_id, topic) VALUES (?, ?)", (aid, topic))
        conn.execute("INSERT OR REPLACE INTO canvas_tagged (assignment_id, tagged_at) VALUES (?, ?)", (aid, when))
        n += 1
    return n


def untagged_count(conn: sqlite3.Connection, cfg: Config) -> int:
    ensure(conn)
    rows = conn.execute(
        "SELECT a.course FROM canvas_assignments a WHERE a.canvas_id NOT IN (SELECT assignment_id FROM canvas_tagged)"
    ).fetchall()
    return sum(1 for r in rows if cfg.course_for(r["course"]) is not None and cfg.is_active(r["course"]))


CREDIT = {"right": 1.0, "partly_right": 0.5, "wrong": 0.0}


def evidence(conn: sqlite3.Connection, course: str) -> list[dict]:
    """Graded, tagged Canvas work as learner-profile evidence. A Canvas quiz with per-question results gives
    one result per question for each of its topics, the same grain as a practice quiz; anything else gives
    one result (its score) per topic."""
    ensure(conn)
    out = []
    per_question = {}
    for r in conn.execute(
        """SELECT q.assignment_id, q.question_id, q.result, s.graded_at, t.topic FROM canvas_quiz_questions q
           JOIN canvas_assignments a ON a.canvas_id = q.assignment_id JOIN canvas_submissions s ON s.assignment_id = a.canvas_id
           JOIN canvas_assignment_topics t ON t.assignment_id = a.canvas_id
           WHERE LOWER(a.course) = LOWER(?) AND s.excused = 0""",
        (course,),
    ):
        per_question.setdefault(r["assignment_id"], []).append(r)
        out.append({"topic": r["topic"], "credit": CREDIT[r["result"]], "mistake": None,
                    "at": r["graded_at"] or _now(), "source": f"canvas {r['assignment_id']}"})
    for r in conn.execute(
        """SELECT a.canvas_id, a.name, a.points, s.score, s.graded_at, s.excused, t.topic FROM canvas_assignment_topics t
           JOIN canvas_assignments a ON a.canvas_id = t.assignment_id JOIN canvas_submissions s ON s.assignment_id = a.canvas_id
           WHERE LOWER(a.course) = LOWER(?) AND s.score IS NOT NULL AND s.excused = 0 AND a.points > 0""",
        (course,),
    ):
        if r["canvas_id"] in per_question:
            continue  # counted question by question above
        out.append({"topic": r["topic"], "credit": max(0.0, min(1.0, r["score"] / r["points"])), "mistake": None,
                    "at": r["graded_at"] or _now(), "source": f"canvas {r['canvas_id']}"})
    return out


def topic_average(conn: sqlite3.Connection, course: str, topics: list[str]) -> tuple[float | None, int]:
    """Average graded Canvas score (percent) on assignments tagged with any of these topics, and how many."""
    ensure(conn)
    if not topics:
        return None, 0
    marks = ",".join("?" * len(topics))
    rows = conn.execute(
        f"""SELECT DISTINCT a.canvas_id, a.points, s.score FROM canvas_assignment_topics t
            JOIN canvas_assignments a ON a.canvas_id = t.assignment_id JOIN canvas_submissions s ON s.assignment_id = a.canvas_id
            WHERE LOWER(a.course) = LOWER(?) AND t.topic IN ({marks}) AND s.score IS NOT NULL AND s.excused = 0 AND a.points > 0""",
        (course, *topics),
    ).fetchall()
    if not rows:
        return None, 0
    return round(100 * sum(r["score"] / r["points"] for r in rows) / len(rows), 1), len(rows)


def missing_on(conn: sqlite3.Connection, course: str, topics: list[str]) -> list[str]:
    ensure(conn)
    if not topics:
        return []
    marks = ",".join("?" * len(topics))
    return [r["name"] for r in conn.execute(
        f"""SELECT DISTINCT a.name FROM canvas_assignment_topics t JOIN canvas_assignments a ON a.canvas_id = t.assignment_id
            JOIN canvas_submissions s ON s.assignment_id = a.canvas_id
            WHERE LOWER(a.course) = LOWER(?) AND t.topic IN ({marks}) AND s.missing = 1 AND s.excused = 0""",
        (course, *topics),
    )]


def raw_dump(conn: sqlite3.Connection, cfg: Config) -> str:
    ensure(conn)
    lines = []
    for c in conn.execute("SELECT * FROM canvas_courses ORDER BY code"):
        grade = f"{c['current_score']:g}%" if c["current_score"] is not None else "no grade yet"
        lines.append(f"{c['code']} | {c['name']} | {grade}" + (f" ({c['current_grade']})" if c["current_grade"] else "") + f" | read {c['read_at']}")
        for r in info(conn, cfg, c["code"], "assignments")["assignments"]:
            flags = ", ".join(f for f, on in (("late", r["late"]), ("missing", r["missing"]), ("excused", r["excused"])) if on)
            score = _fmt_score(r["score"], r["points"]) if r["score"] is not None else "not graded"
            topics = f" [{', '.join(r['topics'])}]" if r["topics"] else ""
            qq = r.get("quiz_questions")
            qtext = f", {qq['right']} of {qq['questions']} questions right (attempt {qq['attempt']} of {qq['attempts']})" if qq else ""
            lines.append(f"  {r['name']} (due {(r['due_at'] or 'no date')[:10]}): {score}" + (f", {flags}" if flags else "") + qtext + topics)
        lines.append("")
    return "\n".join(lines) if lines else "Nothing read from Canvas yet."
