"""Practice habits, from test records only.

Computed in plain Python from quizzes and checks; nothing about how long he studied or what he chatted
about. Once a week the Sunday review asks Claude to turn these numbers into a short narrative (each claim
backed by a number shown below it) and saves the result to `Oso/Profile/Habits.md` through
`save_habits_summary`.

- lead time: for each exam in the period, days between his first practice quiz on its topics and the exam
- follow-through: of the topics he missed, how many he was tested on again within a week, and how many of
  those retests went better
- trend: per course, average quiz score in his first three weeks of practice against his last three
- allocation: per current course, his share of results over the last four weeks, beside the course's
  current grade and the weight of graded work due in the next four weeks
- pace: seconds per question in the quiz window, his first five window quizzes against his last five
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from . import grades, mastery, profile, readiness
from .config import Config
from .db import EFFECTIVE

MIN_DAYS = 14
MIN_RESULTS = 10
RETEST_DAYS = 7
WINDOW_WEEKS = 4


def _parse(ts: str) -> datetime:
    return mastery._parse(ts)


def _all_evidence(conn: sqlite3.Connection, cfg: Config) -> list[dict]:
    out = []
    for c in cfg.courses:
        for e in mastery.evidence(conn, c.code):
            out.append({**e, "course": c.code})
    out.sort(key=lambda e: e["at"])
    return out


def lead_times(conn: sqlite3.Connection, cfg: Config, now: datetime, since: datetime) -> list[dict]:
    out = []
    rows = conn.execute(
        f"""SELECT {EFFECTIVE} FROM items WHERE deleted_at IS NULL AND merged_into IS NULL AND kind = 'exam'
            AND COALESCE(user_due_at, due_at) IS NOT NULL ORDER BY COALESCE(user_due_at, due_at)"""
    ).fetchall()
    for r in rows:
        c = cfg.course_for(r["course_code"])
        if c is None:
            continue
        due = _parse(r["due_at"])
        if not (since <= due <= now):
            continue
        topics = readiness.exam_topics(conn, c.code, r["title"]) or [t["name"] for t in profile.list_topics(conn, c.code)]
        first = None
        for q in readiness._quizzes_on(conn, c.code, topics):
            at = _parse(q["finished_at"])
            if at <= due:
                first = at
                break
        out.append({"course": c.name, "exam": r["title"], "date": due.date().isoformat(),
                    "days_ahead": (due.date() - first.date()).days if first else None})
    return out


def follow_through(evidence: list[dict]) -> dict:
    """A miss starts when a topic goes from right (or untested) to not fully right. It is followed through
    when the topic comes up again in a later quiz or check within a week."""
    missed = retested = improved = 0
    last: dict[tuple[str, str], float] = {}
    for i, e in enumerate(evidence):
        key = (e["course"], e["topic"])
        before = last.get(key)
        last[key] = e["credit"]
        if e["credit"] >= 1.0 or (before is not None and before < 1.0):
            continue
        missed += 1
        at = _parse(e["at"])
        later = [x for x in evidence[i + 1:] if (x["course"], x["topic"]) == key and x["source"] != e["source"]
                 and timedelta(0) <= _parse(x["at"]) - at <= timedelta(days=RETEST_DAYS)]
        if later:
            retested += 1
            if later[0]["credit"] > e["credit"]:
                improved += 1
    return {"missed": missed, "retested_within_week": retested, "retest_improved": improved}


def trends(conn: sqlite3.Connection, cfg: Config) -> list[dict]:
    out = []
    for c in cfg.courses:
        rows = conn.execute(
            "SELECT score, finished_at FROM quizzes WHERE LOWER(course) = LOWER(?) AND finished_at IS NOT NULL AND score IS NOT NULL ORDER BY finished_at",
            (c.code,),
        ).fetchall()
        if len(rows) < 2:
            continue
        start = _parse(rows[0]["finished_at"])
        end = _parse(rows[-1]["finished_at"])
        early = [r["score"] for r in rows if _parse(r["finished_at"]) - start <= timedelta(weeks=3)]
        late = [r["score"] for r in rows if end - _parse(r["finished_at"]) <= timedelta(weeks=3)]
        out.append({"course": c.name, "quizzes": len(rows),
                    "first_three_weeks": round(sum(early) / len(early), 1), "last_three_weeks": round(sum(late) / len(late), 1)})
    return out


def allocation(conn: sqlite3.Connection, cfg: Config, evidence: list[dict], now: datetime) -> list[dict]:
    since = now - timedelta(weeks=WINDOW_WEEKS)
    counts: dict[str, int] = defaultdict(int)
    for e in evidence:
        if _parse(e["at"]) >= since:
            counts[e["course"]] += 1
    total = sum(counts.values())
    horizon = (now + timedelta(weeks=WINDOW_WEEKS)).isoformat(timespec="minutes")
    out = []
    for c in cfg.courses:
        if c.finished:
            continue
        upcoming = conn.execute(
            f"""SELECT SUM(weight) FROM (SELECT {EFFECTIVE} FROM items WHERE deleted_at IS NULL AND merged_into IS NULL)
                WHERE course_code = ? AND due_at >= ? AND due_at <= ?""",
            (c.code, now.isoformat(timespec="minutes"), horizon),
        ).fetchone()[0]
        out.append({"course": c.name, "results": counts.get(c.code, 0),
                    "share_percent": round(100 * counts.get(c.code, 0) / total) if total else 0,
                    "current_grade": grades.summary(conn, c.code).get("current_percent"),
                    "weight_due_next_4_weeks": round(upcoming, 1) if upcoming else 0})
    return out


def pace(conn: sqlite3.Connection) -> dict | None:
    rows = conn.execute(
        """SELECT z.id, SUM(r.seconds) AS secs, COUNT(*) AS n FROM quizzes z
           JOIN quiz_questions q ON q.quiz_id = z.id JOIN quiz_responses r ON r.question_id = q.id
           WHERE z.mode = 'window' AND z.submitted_at IS NOT NULL GROUP BY z.id ORDER BY z.submitted_at"""
    ).fetchall()
    if len(rows) < 2:
        return None
    per = [r["secs"] / r["n"] for r in rows]
    k = min(5, len(per) // 2)
    return {"window_quizzes": len(per), "first_seconds_per_question": round(sum(per[:k]) / k),
            "recent_seconds_per_question": round(sum(per[-k:]) / k)}


def compute(conn: sqlite3.Connection, cfg: Config, now: datetime | None = None) -> dict:
    profile.ensure(conn)
    now = now or datetime.now(UTC)
    ev = _all_evidence(conn, cfg)
    span = (_parse(ev[-1]["at"]) - _parse(ev[0]["at"])).days if ev else 0
    enough = len(ev) >= MIN_RESULTS and span >= MIN_DAYS
    since = _parse(ev[0]["at"]) if ev else now
    return {
        "enough_data": enough,
        "results": len(ev),
        "days_of_records": span,
        "lead_time": lead_times(conn, cfg, now, since),
        "follow_through": follow_through(ev),
        "trend": trends(conn, cfg),
        "allocation": allocation(conn, cfg, ev, now),
        "pace": pace(conn),
    }


def numbers_markdown(h: dict) -> str:
    lines = ["## The numbers", ""]
    lines.append(f"- Results recorded: {h['results']} over {h['days_of_records']} days.")
    lead = h["lead_time"]
    if lead:
        lines.append("- First practice quiz before each exam: " + "; ".join(
            f"{x['course']} {x['exam']} ({x['date']}): " + (f"{x['days_ahead']} days ahead" if x["days_ahead"] is not None else "no practice quiz")
            for x in lead) + ".")
    f = h["follow_through"]
    if f["missed"]:
        lines.append(f"- Topics missed: {f['missed']}; tested again within a week: {f['retested_within_week']}; "
                     f"better on the retest: {f['retest_improved']}.")
    for t in h["trend"]:
        lines.append(f"- {t['course']}: average quiz score {t['first_three_weeks']:.0f}% in the first three weeks of practice, "
                     f"{t['last_three_weeks']:.0f}% in the last three ({t['quizzes']} quizzes).")
    if h["allocation"]:
        lines.append("- Practice over the last four weeks: " + "; ".join(
            f"{a['course']} {a['share_percent']}% of results"
            + (f", grade {a['current_grade']:.0f}%" if a["current_grade"] is not None else "")
            + (f", {a['weight_due_next_4_weeks']:.0f}% of the grade due in the next four weeks" if a["weight_due_next_4_weeks"] else "")
            for a in h["allocation"]) + ".")
    if h["pace"]:
        p = h["pace"]
        lines.append(f"- Pace in the quiz window: {p['first_seconds_per_question']} seconds per question at first, "
                     f"{p['recent_seconds_per_question']} recently ({p['window_quizzes']} quizzes).")
    return "\n".join(lines) + "\n"


def save(cfg: Config, narrative: str, h: dict, now: datetime | None = None) -> str:
    now = now or datetime.now(cfg.tz)
    text = "\n".join([
        "---", "type: oso-habits", f"generated: {now.isoformat(timespec='minutes')}", "---", "",
        "# Practice habits", "",
        "Written weekly by Claude from your quiz and check results; the numbers it is based on are below. "
        "Do not edit; tell Claude if something here is wrong.", "",
        narrative.strip(), "", numbers_markdown(h),
    ])
    from . import vault

    path = vault.write_file(cfg.vault / "Oso" / "Profile" / "Habits.md", text)
    return path.relative_to(cfg.vault).as_posix()
