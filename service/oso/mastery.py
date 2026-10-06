"""Phase 3 of the learner profile: what the student knows, topic by topic.

Every scored result (a graded quiz question or a check of his own work) is evidence about one topic.
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
        """SELECT q.topic, a.result, a.attempts, a.hint, a.mistake, a.answered_at AS at, z.id AS quiz_id
           FROM quiz_answers a JOIN quiz_questions q ON q.id = a.question_id JOIN quizzes z ON z.id = q.quiz_id
           WHERE LOWER(z.course) = LOWER(?)""",
        (course,),
    ):
        credit = CREDIT.get(r["result"], 0.0)
        if (r["attempts"] > 1 or r["hint"]) and credit > 0.5:
            credit = 0.5
        out.append({"topic": r["topic"], "credit": credit, "mistake": r["mistake"], "at": r["at"], "source": f"quiz {r['quiz_id']}"})
    for r in conn.execute(
        "SELECT id, topic, correct, mistake, checked_at FROM checks WHERE LOWER(course) = LOWER(?)", (course,)
    ):
        out.append({"topic": r["topic"], "credit": 1.0 if r["correct"] else 0.0, "mistake": r["mistake"],
                    "at": r["checked_at"], "source": f"check {r['id']}"})
    out.sort(key=lambda e: e["at"])
    return out


def topic_states(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    by_topic: dict[str, list[dict]] = {}
    for e in evidence(conn, course):
        by_topic.setdefault(e["topic"], []).append(e)
    listed = profile.list_topics(conn, course)
    names = [t["name"] for t in listed] + [n for n in by_topic if n not in {t["name"] for t in listed}]
    meta = {t["name"]: t for t in listed}
    out = []
    for name in names:
        ev = by_topic.get(name, [])
        row = {"topic": name, "week": meta.get(name, {}).get("week"), "exams": meta.get(name, {}).get("exams", []),
               "results": len(ev), "accuracy": None, "last_practiced": None, "trend": None, "common_mistake": None,
               "sources": sorted({e["source"] for e in ev}, key=lambda s: (s.split()[0], int(s.split()[1])))}
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
        recent = sum(1 for e in ev if now - _parse(e["at"]) <= timedelta(days=RECENT_DAYS))
        if len(ev) < cfg.untested_below:
            row["state"] = "untested"
        elif row["accuracy"] >= cfg.strong_percent and recent >= cfg.strong_min_results:
            row["state"] = "strong"
        else:
            row["state"] = "shaky"
        out.append(row)
    return out


def course_profile(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None) -> dict:
    c = cfg.course_for(course)
    if c is None:
        raise profile.ProfileError(f"There is no course {course!r}; use its code from list_courses.")
    topics = topic_states(conn, cfg, c.code, now)
    return {
        "course": c.code,
        "name": c.name,
        "shaky": [t for t in topics if t["state"] == "shaky"],
        "untested": [t for t in topics if t["state"] == "untested"],
        "strong": [t for t in topics if t["state"] == "strong"],
    }


MISTAKE_WORDS = {"concept_gap": "concept gaps", "calculation_slip": "calculation slips",
                 "misread_question": "misread questions", "incomplete": "incomplete answers"}


def render(p: dict, cfg: Config, now: datetime) -> str:
    lines = [
        "---",
        "type: oso-profile",
        f"course: {p['course']}",
        f"generated: {now.isoformat(timespec='minutes')}",
        "---",
        "",
        f"# {p['name']}: what you know",
        "",
        "Generated by Oso from your quiz results and checks of your work. Do not edit; it is rewritten on every check. "
        "If something here is wrong, tell Claude.",
        "",
        f"Strong means {cfg.strong_percent}% or better over at least {cfg.strong_min_results} recent results; "
        f"untested means fewer than {cfg.untested_below} results. Recent results count more.",
        "",
    ]
    for heading, key, empty in (("Needs work", "shaky", "Nothing shaky right now."),
                                ("Not yet tested", "untested", "Every topic has been tested."),
                                ("Strong", "strong", "No strong topics yet.")):
        lines.append(f"## {heading}")
        rows = p[key]
        if not rows:
            lines.append(f"- {empty}")
        for t in rows:
            bits = []
            if t["accuracy"] is not None:
                bits.append(f"{t['accuracy']:.0f}% over {t['results']} result{'s' if t['results'] != 1 else ''}")
            if t["trend"]:
                bits.append(t["trend"])
            if t["common_mistake"]:
                bits.append(f"mostly {MISTAKE_WORDS.get(t['common_mistake'], t['common_mistake'])}")
            if t["last_practiced"]:
                bits.append(f"last practiced {t['last_practiced']}")
            if t["exams"]:
                bits.append("on " + ", ".join(t["exams"]))
            if t["sources"]:
                bits.append("from " + ", ".join(t["sources"][-6:]))
            lines.append(f"- **{t['topic']}**" + (f": {'; '.join(bits)}" if bits else ""))
        lines.append("")
    return "\n".join(lines)


def write_all(conn: sqlite3.Connection, cfg: Config, now: datetime | None = None) -> list[Path]:
    now = now or datetime.now(cfg.tz)
    folder = cfg.vault / "Oso" / "Profile"
    written = []
    for c in cfg.courses:
        p = course_profile(conn, cfg, c.code, now)
        if not (p["shaky"] or p["untested"] or p["strong"]):
            continue
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{c.name} ({c.term}).md" if c.term else f"{c.name}.md"
        path = folder / name.replace("/", "-")
        text = render(p, cfg, now)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old is None or old.split("---", 2)[-1] != text.split("---", 2)[-1]:
            path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
