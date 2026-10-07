"""What the student knows, topic by topic.

Every scored result (a graded quiz question, a check of his own work, or graded Canvas work tagged with
the topic) is evidence about one topic.
Plain arithmetic turns that evidence into a state per topic:

- credit: right 1, partly right 0.5, wrong or skipped 0. A quiz question he only got right after another
  try or a hint earns at most 0.5: he needed help. A check earns 1 if his attempt was right as submitted.
- weight: recent results count more; a result `half_life_days` old counts half as much as today's.
- accuracy: weighted average of credit.
- state: **untested** with fewer than `untested_below` results; **strong** at `strong_percent` or better
  with at least `strong_min_results` results in the last 60 days; otherwise **shaky**.
- trend: the last five results against the five before them; 15 points or more either way is improving
  or slipping.

Every topic on the course's list appears, so a topic he has never been tested on shows as untested
rather than disappearing. The summary is written to `Oso/Profile/<course>.md` on every check.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import profile
from .config import Config

CREDIT = {"right": 1.0, "partly_right": 0.5, "wrong": 0.0, "skipped": 0.0}
RECENT_DAYS = 60
TREND_WINDOW = 5
TREND_POINTS = 15


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def evidence(conn: sqlite3.Connection, course: str) -> list[dict]:
    """Every scored result for a course, oldest first."""
    profile.ensure(conn)
    out = []
    for r in conn.execute(
        """SELECT q.topic, q.difficulty, q.misconception_id, a.result, a.attempts, a.hint, a.mistake, a.answered_at AS at,
                  z.id AS quiz_id
           FROM quiz_answers a JOIN quiz_questions q ON q.id = a.question_id JOIN quizzes z ON z.id = q.quiz_id
           WHERE LOWER(z.course) = LOWER(?)""",
        (course,),
    ):
        credit = CREDIT.get(r["result"], 0.0)
        if (r["attempts"] > 1 or r["hint"]) and credit > 0.5:
            credit = 0.5
        out.append({"topic": r["topic"], "credit": credit, "mistake": r["mistake"], "at": r["at"], "source": f"quiz {r['quiz_id']}",
                    "difficulty": r["difficulty"]})
    for r in conn.execute(
        "SELECT id, topic, correct, mistake, checked_at FROM checks WHERE LOWER(course) = LOWER(?)", (course,)
    ):
        out.append({"topic": r["topic"], "credit": 1.0 if r["correct"] else 0.0, "mistake": r["mistake"],
                    "at": r["checked_at"], "source": f"check {r['id']}"})
    from . import canvas_store

    out.extend(canvas_store.evidence(conn, course))  # graded Canvas work tagged with topics
    out.sort(key=lambda e: e["at"])
    return out


def topic_states(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None, record: bool = False) -> list[dict]:
    now = now or datetime.now(UTC)
    by_topic: dict[str, list[dict]] = {}
    for e in evidence(conn, course):
        by_topic.setdefault(e["topic"], []).append(e)
    listed = profile.list_topics(conn, course)
    names = [t["name"] for t in listed] + [n for n in by_topic if n not in {t["name"] for t in listed}]
    meta = {t["name"]: t for t in listed}
    from . import tutor

    stages = {t["topic"]: t for t in tutor.topics(conn, cfg, course, now, record=record)}
    names += [n for n in stages if n not in names]
    out = []
    for name in names:
        ev = by_topic.get(name, [])
        row = {"topic": name, "week": meta.get(name, {}).get("week"), "exams": meta.get(name, {}).get("exams", []),
               "results": len(ev), "accuracy": None, "last_practiced": None, "trend": None, "common_mistake": None,
               "sources": sorted({e["source"] for e in ev}, key=lambda s: (s.split()[0], int(s.split()[1]) if s.split()[1].isdigit() else 0))}
        if ev:
            weights = [0.5 ** ((now - _parse(e["at"])).total_seconds() / 86400 / cfg.half_life_days) for e in ev]
            row["accuracy"] = round(100 * sum(w * e["credit"] for w, e in zip(weights, ev)) / sum(weights), 1)
            row["last_practiced"] = ev[-1]["at"][:10]
            mistakes = Counter(e["mistake"] for e in ev if e["mistake"])
            row["common_mistake"] = mistakes.most_common(1)[0][0] if mistakes else None
            if len(ev) > TREND_WINDOW:
                last = ev[-TREND_WINDOW:]
                before = ev[-2 * TREND_WINDOW:-TREND_WINDOW]
                diff = 100 * (sum(e["credit"] for e in last) / len(last) - sum(e["credit"] for e in before) / len(before))
                row["trend"] = "improving" if diff >= TREND_POINTS else "slipping" if diff <= -TREND_POINTS else "steady"
        t = stages.get(name, {})
        row.update({k: t.get(k) for k in ("stage", "next_step", "status", "misconceptions", "trail")})
        # The older three-way rating, kept for readiness and the briefing: solid and maintaining are strong.
        row["state"] = {"solid": "strong", "maintaining": "strong", "untested": "untested"}.get(t.get("stage"), "shaky")
        out.append(row)
    return out


def course_profile(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None, record: bool = False) -> dict:
    """Topics grouped by stage, with the older strong/shaky/untested groups the briefing and readiness use."""
    c = cfg.course_for(course)
    if c is None:
        raise profile.ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    from . import tutor

    now = now or datetime.now(UTC)
    topics = topic_states(conn, cfg, c.code, now, record=record)
    flags = tutor.course_flags(conn, cfg, c.code, now=now)
    return {
        "course": c.code,
        "name": c.name,
        "topics": topics,
        "flags": {k: v["line"] for k, v in flags.items()},
        "goal": tutor.goal(conn, c.code),
        "shaky": [t for t in topics if t["state"] == "shaky"],
        "untested": [t for t in topics if t["state"] == "untested"],
        "strong": [t for t in topics if t["state"] == "strong"],
    }


MISTAKE_WORDS = {"concept_gap": "concept gaps", "calculation_slip": "calculation slips",
                 "misread_question": "misread questions", "incomplete": "incomplete answers"}

GROUPS = (("Needs focus", ("needs_focus",)), ("Explained, not yet shown", ("explained",)), ("Practicing", ("practicing",)),
          ("Not yet tested", ("untested",)), ("Solid", ("solid", "maintaining")))


def render(p: dict, cfg: Config, now: datetime) -> str:
    lines = [
        "---",
        "type: oso-profile",
        f"course: {p['course']}",
        f"generated: {now.isoformat(timespec='minutes')}",
        "---",
        "",
        f"# {p['name']}: where you stand",
        "",
        "Generated by Oso from your quizzes, checks of your work, graded Canvas work, and what you've shown in conversations "
        "with Claude. Do not edit; it is rewritten on every check. If something here is wrong, tell Claude.",
        "",
        f"Solid means {cfg.strong_percent}% or better over at least {cfg.strong_min_results} recent results, including medium or "
        "hard questions, and explaining it correctly in your own words. Recent results count more; nothing from conversation "
        "alone makes a topic solid.",
        "",
    ]
    if p.get("goal"):
        lines += [f"Your goal: {p['goal']['goal']}.", ""]
    if p.get("flags"):
        lines.append("## Heads up")
        lines += [f"- {line}" for line in p["flags"].values()]
        lines.append("")
    for heading, stages in GROUPS:
        rows = [t for t in p["topics"] if t.get("stage") in stages]
        if not rows:
            continue
        lines.append(f"## {heading}")
        for t in rows:
            bits = [t["status"].split(": ", 1)[1] if t.get("status") else ""]
            if t.get("common_mistake"):
                bits.append(f"mostly {MISTAKE_WORDS.get(t['common_mistake'], t['common_mistake'])}")
            if t.get("exams"):
                bits.append("on " + ", ".join(t["exams"]))
            lines.append(f"- **{t['topic']}**: {'; '.join(b for b in bits if b)}. Next: {t['next_step']}.")
            if t.get("trail"):
                lines.append(f"  - Trail: {t['trail']}")
        lines.append("")
    return "\n".join(lines)


def write_all(conn: sqlite3.Connection, cfg: Config, now: datetime | None = None) -> list[Path]:
    from . import tutor

    now = now or datetime.now(cfg.tz)
    folder = cfg.vault / "Oso" / "Profile"
    written = []
    for c in cfg.courses:
        p = course_profile(conn, cfg, c.code, now, record=True)
        if not p["topics"]:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{c.name} ({c.term}).md" if c.term else f"{c.name}.md"
        path = folder / name.replace("/", "-")
        text = render(p, cfg, now)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old is None or old.split("---", 2)[-1] != text.split("---", 2)[-1]:
            path.write_text(text, encoding="utf-8")
        written.append(path)
    how = tutor.write_how_i_learn(conn, cfg, now)
    if how:
        written.append(how)
    return written
