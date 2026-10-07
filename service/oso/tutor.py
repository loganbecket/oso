"""A study partner that knows him: what he shows in conversation, a trajectory for every topic, and honest
verdicts computed from evidence.

**Conversation notes.** Oso can't read conversations afterward, so Claude notes what it sees as it happens
(`note_signal`): confusion, a misconception (kept as the wrong idea itself, open until he shows it fixed), a
basic question, explaining an idea well in his own words, solving a problem in chat with or without help, an
explanation Claude gave, a preference about how he learns, or a goal. A repeat within a couple of hours is
folded into the note already there.

**Trajectories.** Every topic gets a stage, worked out here in plain arithmetic from all the evidence
(conversation notes, practice quizzes, checks of his work, graded Canvas work), never declared by Claude:

- untested: no evidence yet. Next: find out.
- needs focus: recent confusion, an open misconception, or weak results. Next: explain, then check.
- explained: Claude has explained it since the confusion and nothing has shown it since. Next: check understanding.
- practicing: some understanding shown; results mixed or few. Next: practice.
- solid: strong recent results, including medium or hard questions, plus a good explanation in his own words. Next: review now and then.
- maintaining: solid for three weeks. Next: light review; due for review after four weeks without practice.

Conversation evidence steers but never confirms: confusion counts like a wrong practice answer, explaining it
well like half a right one, and nothing from conversation alone can make a topic solid.

**Honesty checks** (computed, so Claude can't talk them away): practice running well above real grades on the
same topics, and "hard" questions that turn out easy.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import profile
from .config import Config

KINDS = ("confused", "misconception", "basic_question", "explained_well", "solved", "needed_help", "explained",
         "preference", "goal")
NEGATIVE = {"confused", "misconception", "basic_question"}
# What conversation evidence counts for, against a practice result (1 right, 0 wrong). Claude's own
# explanation ("explained") and preferences and goals are not evidence about what he knows.
CONVERSATION_CREDIT = {"confused": 0.0, "misconception": 0.0, "basic_question": 0.0, "explained_well": 0.5, "solved": 0.5,
                       "needed_help": 0.25}
FOLD_HOURS = 2
RECENT_DAYS = 60
CONFUSION_DAYS = 21  # unresolved confusion this recent keeps a topic in focus
WEAK_PERCENT = 60  # results below this need focus
MAINTAIN_DAYS = 21
REVIEW_DAYS = 28
REALITY_POINTS = 15
REALITY_ASSESSMENTS = 2
SURE_WRONG_DAYS = 14

STAGES = ("untested", "needs_focus", "explained", "practicing", "solid", "maintaining")
STAGE_WORDS = {"untested": "untested", "needs_focus": "needs focus", "explained": "explained, not yet shown",
               "practicing": "practicing", "solid": "solid", "maintaining": "maintaining"}
NEXT = {"untested": "a few questions to find out",
        "needs_focus": "explain it, then check understanding",
        "explained": "check understanding: explain it back in your own words, or one quick question",
        "practicing": "practice",
        "solid": "review now and then",
        "maintaining": "light review only"}

STANDING_RULE = (
    "Be a direct, honest tutor. Report where he stands from Oso's measured status, never your impression, and name the "
    "evidence for anything positive. Lead with gaps and mistakes. No unearned praise, no \"great question,\" no softening a "
    "wrong answer. Grade against the stored criteria; don't change a grade under pushback unless the criteria support it. "
    "Say plainly when you're unsure."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY,
    course           TEXT,
    topic            TEXT,
    kind             TEXT NOT NULL,
    words            TEXT,             -- his words where they show it, or what Claude explained and how
    misconception_id INTEGER,
    times            INTEGER NOT NULL DEFAULT 1,  -- repeats folded in
    at               TEXT NOT NULL,
    last_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS misconceptions (
    id         INTEGER PRIMARY KEY,
    course     TEXT NOT NULL,
    topic      TEXT NOT NULL,
    belief     TEXT NOT NULL,          -- the wrong idea itself
    opened_at  TEXT NOT NULL,
    closed_at  TEXT,
    closed_by  TEXT                    -- what showed it fixed
);
CREATE TABLE IF NOT EXISTS goals (
    course     TEXT PRIMARY KEY,
    goal       TEXT NOT NULL,          -- as he said it
    target     REAL,                   -- percent, when the goal is a grade
    set_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topic_stages (
    course     TEXT NOT NULL,
    topic      TEXT NOT NULL,
    stage      TEXT NOT NULL,
    since      TEXT NOT NULL,
    PRIMARY KEY (course, topic)
);
CREATE TABLE IF NOT EXISTS regrades (
    id          INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,
    old         TEXT,
    new         TEXT NOT NULL,
    reason      TEXT NOT NULL,
    at          TEXT NOT NULL
);
"""


class TutorError(ValueError):
    """A plain-sentence problem with what a skill tried to record."""


def ensure(conn: sqlite3.Connection) -> None:
    profile.ensure(conn)
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


# ---- conversation notes ---------------------------------------------------------------------------------


def note_signal(conn: sqlite3.Connection, cfg: Config, kind: str, course: str | None = None, topic: str | None = None,
                words: str | None = None, belief: str | None = None, misconception_id: int | None = None,
                target: float | None = None, now: str | None = None) -> dict:
    """Keep one thing he showed in conversation. Returns what was kept (and the misconception's id, to aim at later)."""
    ensure(conn)
    kind = str(kind or "").strip().lower().replace(" ", "_")
    if kind not in KINDS:
        raise TutorError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}.")
    when = now or _now()
    code = None
    if course:
        c = cfg.course_for(course)
        if c is None:
            raise TutorError(f"There is no course {course!r}; use its code from list_courses.")
        code = c.code
    if kind == "goal":
        if not code or not (words or target):
            raise TutorError("A goal needs the course and what he said.")
        conn.execute("INSERT OR REPLACE INTO goals (course, goal, target, set_at) VALUES (?, ?, ?, ?)",
                     (code, (words or f"{target:g}%").strip(), target if target is None else float(target), when))
        return {"kept": "goal", "course": code}
    if kind != "preference":
        if not code or not topic:
            raise TutorError(f"A {kind.replace('_', ' ')} note needs the course and the topic.")
        topic = profile.match_topic(conn, code, topic, when)
    if kind == "misconception":
        belief = (belief or words or "").strip()
        if not belief:
            raise TutorError("A misconception needs the wrong idea itself, in a sentence.")
        same = [m for m in conn.execute("SELECT * FROM misconceptions WHERE course = ? AND topic = ? AND closed_at IS NULL", (code, topic))
                if _similar(m["belief"], belief)]
        if same:
            misconception_id = same[0]["id"]
        else:
            misconception_id = int(conn.execute(
                "INSERT INTO misconceptions (course, topic, belief, opened_at) VALUES (?, ?, ?, ?)", (code, topic, belief, when)
            ).lastrowid)
    if misconception_id is not None and kind in ("explained_well", "solved"):
        close_misconception(conn, misconception_id, f"explained it correctly in conversation ({when[:10]})", when)
    # A repeat within a couple of hours is the same moment of the same conversation: fold it in.
    since = (_parse(when) - timedelta(hours=FOLD_HOURS)).isoformat(timespec="seconds")
    prior = conn.execute(
        """SELECT id FROM signals WHERE kind = ? AND COALESCE(course, '') = COALESCE(?, '') AND COALESCE(topic, '') = COALESCE(?, '')
           AND COALESCE(misconception_id, 0) = COALESCE(?, 0) AND last_at >= ? AND kind != 'preference' ORDER BY id DESC LIMIT 1""",
        (kind, code, topic, misconception_id, since),
    ).fetchone()
    if prior:
        conn.execute("UPDATE signals SET times = times + 1, last_at = ?, words = COALESCE(?, words) WHERE id = ?",
                     (when, (words or "").strip() or None, prior["id"]))
        sid = prior["id"]
    else:
        sid = int(conn.execute(
            "INSERT INTO signals (course, topic, kind, words, misconception_id, at, last_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, topic, kind, (words or "").strip() or None, misconception_id, when, when),
        ).lastrowid)
    out = {"kept": kind, "note": sid, "course": code, "topic": topic}
    if misconception_id is not None:
        out["misconception"] = misconception_id
    return out


def _similar(a: str, b: str) -> bool:
    wa, wb = set(re.findall(r"[a-z]{3,}", a.lower())), set(re.findall(r"[a-z]{3,}", b.lower()))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def close_misconception(conn: sqlite3.Connection, mid: int, how: str, when: str | None = None) -> None:
    conn.execute("UPDATE misconceptions SET closed_at = ?, closed_by = ? WHERE id = ? AND closed_at IS NULL", (when or _now(), how, mid))


def forget(conn: sqlite3.Connection, note: int | None = None, misconception: int | None = None, reopen: bool = False) -> str:
    """Correct the record when he says a note is wrong: remove a note, or remove or reopen a misconception."""
    ensure(conn)
    if note is not None:
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (note,)).fetchone()
        if row is None:
            raise TutorError(f"There is no note {note}.")
        conn.execute("DELETE FROM signals WHERE id = ?", (note,))
        return f"Removed the note that he was {row['kind'].replace('_', ' ')}{' on ' + row['topic'] if row['topic'] else ''}."
    if misconception is not None:
        row = conn.execute("SELECT * FROM misconceptions WHERE id = ?", (misconception,)).fetchone()
        if row is None:
            raise TutorError(f"There is no misconception {misconception}.")
        if reopen:
            conn.execute("UPDATE misconceptions SET closed_at = NULL, closed_by = NULL WHERE id = ?", (misconception,))
            return f"Reopened: {row['belief']}"
        conn.execute("DELETE FROM misconceptions WHERE id = ?", (misconception,))
        conn.execute("UPDATE signals SET misconception_id = NULL WHERE misconception_id = ?", (misconception,))
        return f"Removed the misconception: {row['belief']}"
    raise TutorError("Say which note or misconception to correct.")


# ---- the evidence ----------------------------------------------------------------------------------------


def evidence(conn: sqlite3.Connection, course: str) -> list[dict]:
    """Every result and conversation note for a course, oldest first. Results carry `test` True (they can confirm);
    conversation notes `test` False (they only steer)."""
    from . import mastery

    ensure(conn)
    out = [dict(e, test=True) for e in mastery.evidence(conn, course)]
    for s in conn.execute("SELECT * FROM signals WHERE LOWER(course) = LOWER(?) AND topic IS NOT NULL", (course,)):
        out.append({"topic": s["topic"], "credit": CONVERSATION_CREDIT.get(s["kind"]), "mistake": None, "at": s["at"],
                    "source": "chat", "kind": s["kind"], "words": s["words"], "test": False, "note": s["id"]})
    out.sort(key=lambda e: e["at"])
    return out


def _weighted(ev: list[dict], now: datetime, half_life: int) -> float | None:
    scored = [e for e in ev if e.get("credit") is not None]
    if not scored:
        return None
    weights = [0.5 ** ((now - _parse(e["at"])).total_seconds() / 86400 / half_life) for e in scored]
    return 100 * sum(w * e["credit"] for w, e in zip(weights, scored)) / sum(weights)


def open_misconceptions(conn: sqlite3.Connection, course: str, topic: str | None = None) -> list[dict]:
    ensure(conn)
    q = "SELECT * FROM misconceptions WHERE LOWER(course) = LOWER(?) AND closed_at IS NULL"
    args: list = [course]
    if topic:
        q += " AND topic = ?"
        args.append(topic)
    return [{"id": r["id"], "topic": r["topic"], "belief": r["belief"], "since": r["opened_at"][:10]} for r in conn.execute(q + " ORDER BY id", args)]


# ---- the trajectory ----------------------------------------------------------------------------------------


def stage_for(ev: list[dict], misconceptions: list[dict], cfg: Config, now: datetime, reality_flagged: bool = False,
              prior: dict | None = None) -> dict:
    """One topic's stage and next step from its evidence, by the rules in this module's docstring."""
    tests = [e for e in ev if e["test"]]
    talk = [e for e in ev if not e["test"]]
    accuracy = _weighted([e for e in ev if e.get("credit") is not None], now, cfg.half_life_days)
    test_accuracy = _weighted(tests, now, cfg.half_life_days)
    # Confusion is resolved by a later good result or by explaining it well.
    negatives = [e for e in talk if e["kind"] in NEGATIVE]
    unresolved = []
    for n in negatives:
        later = [e for e in ev if e["at"] > n["at"] and ((e["test"] and e["credit"] >= 0.75) or e.get("kind") == "explained_well")]
        if not later and now - _parse(n["at"]) <= timedelta(days=CONFUSION_DAYS):
            unresolved.append(n)
    weak = len(tests) >= cfg.untested_below and test_accuracy is not None and test_accuracy < WEAK_PERCENT
    last_negative = max((n["at"] for n in unresolved), default=None)
    explained_since = last_negative and any(e.get("kind") == "explained" and e["at"] >= last_negative for e in talk)
    tested_since = last_negative and any(e["test"] and e["at"] > last_negative for e in tests)
    why: list[str] = []
    if misconceptions or unresolved or weak:
        if misconceptions:
            why.append("open misconception: " + "; ".join(m["belief"] for m in misconceptions))
        if unresolved:
            why.append("unresolved: " + ", ".join(_describe(n) for n in unresolved[-2:]))
        if weak:
            why.append(f"results at {test_accuracy:.0f}%")
        stage = "explained" if explained_since and not tested_since and not weak else "needs_focus"
        return _result(stage, NEXT[stage], why, accuracy, tests, talk)
    if not tests and not [e for e in talk if e["kind"] in CONVERSATION_CREDIT]:
        return _result("untested", NEXT["untested"], [], accuracy, tests, talk)
    if len(tests) < cfg.untested_below:
        stage = "practicing" if talk else "untested"
        return _result(stage, NEXT[stage] if stage == "untested" else "practice: a few more questions", [], accuracy, tests, talk)
    recent = [e for e in tests if now - _parse(e["at"]) <= timedelta(days=RECENT_DAYS)]
    strong = test_accuracy is not None and test_accuracy >= cfg.strong_percent and len(recent) >= cfg.strong_min_results
    beyond_easy = any(e.get("difficulty") in ("medium", "hard") or e["source"].startswith("canvas") for e in recent)
    explained_well = any(e.get("kind") == "explained_well" for e in talk)
    real_agrees = not reality_flagged or any(e["source"].startswith("canvas") for e in recent)
    if strong and beyond_easy and explained_well and real_agrees:
        stage = "solid"
        since = prior["since"] if prior and prior["stage"] in ("solid", "maintaining") else now.isoformat(timespec="seconds")
        if now - _parse(since) >= timedelta(days=MAINTAIN_DAYS):
            stage = "maintaining"
        last_test = _parse(tests[-1]["at"])
        step = NEXT[stage]
        if now - last_test >= timedelta(days=REVIEW_DAYS):
            step = f"due for review (last practiced {last_test.date().isoformat()})"
        return _result(stage, step, [], accuracy, tests, talk)
    step = "practice"
    if strong and not beyond_easy:
        step = "practice with medium or hard questions; easy ones alone don't show it"
    elif strong and not explained_well:
        step = "explain it in your own words; the results are there"
    elif strong and not real_agrees:
        step = "practice at the level of real graded work; practice has been easier than the real thing"
    return _result("practicing", step, [], accuracy, tests, talk)


def _describe(e: dict) -> str:
    words = f" ('{e['words'][:80]}')" if e.get("words") else ""
    return f"{e['kind'].replace('_', ' ')} {e['at'][:10]}{words}"


def _result(stage: str, step: str, why: list[str], accuracy, tests: list[dict], talk: list[dict]) -> dict:
    return {"stage": stage, "next_step": step, "why": why, "accuracy": round(accuracy, 1) if accuracy is not None else None,
            "results": len(tests), "notes": len(talk)}


def status_line(topic: str, row: dict, tests: list[dict]) -> str:
    """The plain verdict Claude reports: recent results, open problems, stage."""
    bits = []
    last = tests[-5:]
    if last:
        right = sum(1 for e in last if e["credit"] >= 1)
        bits.append(f"{right} of {len(last)} right in the last {len(last)} result{'s' if len(last) != 1 else ''} "
                    f"({last[0]['at'][:10]} to {last[-1]['at'][:10]})")
    else:
        bits.append("no results yet")
    bits += row["why"]
    return f"{topic}: {'; '.join(bits)}; {STAGE_WORDS[row['stage']]}"


def trail(ev: list[dict]) -> str:
    """The dated trail behind a stage: "confused 2026-10-03 ('...'); explained 2026-10-03; quiz 5 2026-10-05, 3 of 3"."""
    parts, groups = [], {}
    for e in ev:
        if not e["test"]:
            parts.append((e["at"], _describe(e) if e["kind"] in NEGATIVE else f"{e['kind'].replace('_', ' ')} {e['at'][:10]}"))
            continue
        g = groups.setdefault(e["source"], {"at": e["at"], "n": 0, "right": 0})
        g["n"] += 1
        g["right"] += 1 if e["credit"] >= 1 else 0
    for src, g in groups.items():
        parts.append((g["at"], f"{src} {g['at'][:10]}, {g['right']} of {g['n']}"))
    return "; ".join(p for _, p in sorted(parts)[-8:])


def course_flags(conn: sqlite3.Connection, cfg: Config, course: str, ev: list[dict] | None = None, now: datetime | None = None) -> dict:
    """The honesty checks for one course, from evidence alone."""
    now = now or datetime.now(UTC)
    ev = ev if ev is not None else evidence(conn, course)
    flags: dict = {}
    # Practice against reality: each graded Canvas assessment against his practice on the same topics.
    practice = [e for e in ev if e["test"] and not e["source"].startswith("canvas")]
    gaps = []
    for src in dict.fromkeys(e["source"] for e in ev if e["source"].startswith("canvas")):
        real = [e for e in ev if e["source"] == src]
        topics = {e["topic"] for e in real}
        mine = [e for e in practice if e["topic"] in topics]
        if mine:
            gaps.append(100 * (sum(e["credit"] for e in mine) / len(mine) - sum(e["credit"] for e in real) / len(real)))
    if len(gaps) >= REALITY_ASSESSMENTS:
        gap = sum(gaps) / len(gaps)
        if gap >= REALITY_POINTS:
            flags["practice_too_easy"] = {"points": round(gap), "assessments": len(gaps),
                                          "line": f"Practice scores run about {gap:.0f} points higher than real graded work on the same topics "
                                                  f"({len(gaps)} assessments); practice is too easy."}
    # Difficulty labels against results.
    hard = [e for e in ev if e["test"] and e.get("difficulty") == "hard"][-10:]
    if len(hard) >= 5 and sum(e["credit"] for e in hard) / len(hard) >= 0.9:
        flags["hard_too_easy"] = {"line": f"He got {sum(1 for e in hard if e['credit'] >= 1)} of the last {len(hard)} \"hard\" questions right; "
                                          "write harder hard questions."}
    return flags


def topics(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None, record: bool = False) -> list[dict]:
    """Every topic in a course with its stage, next step, status line, misconceptions, and trail."""
    ensure(conn)
    now = now or datetime.now(UTC)
    ev = evidence(conn, course)
    flags = course_flags(conn, cfg, course, ev, now)
    by_topic: dict[str, list[dict]] = {}
    for e in ev:
        by_topic.setdefault(e["topic"], []).append(e)
    listed = profile.list_topics(conn, course)
    names = [t["name"] for t in listed] + [n for n in by_topic if n not in {t["name"] for t in listed}]
    meta = {t["name"]: t for t in listed}
    priors = {r["topic"]: dict(r) for r in conn.execute("SELECT * FROM topic_stages WHERE LOWER(course) = LOWER(?)", (course,))}
    out = []
    for name in names:
        t_ev = by_topic.get(name, [])
        mis = open_misconceptions(conn, course, name)
        row = stage_for(t_ev, mis, cfg, now, "practice_too_easy" in flags, priors.get(name))
        tests = [e for e in t_ev if e["test"]]
        row.update({"topic": name, "week": meta.get(name, {}).get("week"), "exams": meta.get(name, {}).get("exams", []),
                    "misconceptions": mis, "status": status_line(name, row, tests), "trail": trail(t_ev),
                    "last_practiced": tests[-1]["at"][:10] if tests else None})
        prior = priors.get(name)
        family = "solid" if row["stage"] in ("solid", "maintaining") else row["stage"]
        old_family = "solid" if prior and prior["stage"] in ("solid", "maintaining") else (prior or {}).get("stage")
        row["became_solid"] = family == "solid" and old_family != "solid"
        if record and family != old_family:
            conn.execute("INSERT OR REPLACE INTO topic_stages (course, topic, stage, since) VALUES (?, ?, ?, ?)",
                         (course, name, family, now.isoformat(timespec="seconds")))
        out.append(row)
    return out


# ---- goals, standing, and where time should go -----------------------------------------------------------


def goal(conn: sqlite3.Connection, course: str) -> dict | None:
    ensure(conn)
    r = conn.execute("SELECT * FROM goals WHERE LOWER(course) = LOWER(?)", (course,)).fetchone()
    return dict(r) if r else None


def current_percent(conn: sqlite3.Connection, course: str) -> float | None:
    """His current grade: Canvas's own number when Oso reads Canvas, else Oso's calculation from recorded grades."""
    try:
        r = conn.execute("SELECT current_score FROM canvas_courses WHERE LOWER(code) = LOWER(?)", (course,)).fetchone()
        if r and r["current_score"] is not None:
            return float(r["current_score"])
    except sqlite3.Error:
        pass
    from . import grades

    return grades.summary(conn, course).get("current_percent")


def attention(conn: sqlite3.Connection, cfg: Config, now: datetime | None = None) -> list[dict]:
    """How much attention each active course needs, most first, with the reasons and a share of study time.
    From topics needing focus, the next exam's closeness, the grade against his stated goal, and upcoming work."""
    from .db import EFFECTIVE

    ensure(conn)
    now = now or datetime.now(cfg.tz)
    soon = (now + timedelta(days=14)).isoformat(timespec="minutes")
    out = []
    for c in cfg.courses:
        if c.finished:
            continue
        ts = topics(conn, cfg, c.code, now)
        focus = [t["topic"] for t in ts if t["stage"] in ("needs_focus", "explained")]
        practicing = [t["topic"] for t in ts if t["stage"] == "practicing"]
        items = conn.execute(
            f"""SELECT kind, {EFFECTIVE} FROM items WHERE deleted_at IS NULL AND merged_into IS NULL
                AND COALESCE(user_course, course_code) = ? AND due_at >= ? AND due_at <= ?""",
            (c.code, now.isoformat(timespec="minutes"), soon),
        ).fetchall()
        items = [r for r in items if r["status"] != "done"]
        exams = sorted(r["due_at"] for r in items if r["kind"] == "exam")
        score, reasons = 0.0, []
        if focus:
            score += 2 * len(focus)
            reasons.append(f"{len(focus)} topic{'s' if len(focus) != 1 else ''} need focus ({', '.join(focus[:3])})")
        score += 0.5 * len(practicing)
        if exams:
            days = max(0, (datetime.fromisoformat(exams[0]).date() - now.date()).days)
            score += 10 / (days + 1)
            reasons.append(f"exam in {days} day{'s' if days != 1 else ''}")
        g, cur = goal(conn, c.code), current_percent(conn, c.code)
        if g and g.get("target") is not None and cur is not None and cur < g["target"]:
            score += (g["target"] - cur) / 2
            reasons.append(f"at {cur:g}% against his goal of {g['target']:g}%")
        weight = sum(r["weight"] or 0 for r in items)
        if weight:
            score += weight / 10
            reasons.append(f"{weight:g}% of the grade due in two weeks")
        out.append({"course": c.code, "name": c.name, "score": round(score, 1), "reasons": reasons, "goal": g, "current_percent": cur})
    total = sum(x["score"] for x in out) or 1
    for x in out:
        x["share_percent"] = round(100 * x["score"] / total)
    return sorted(out, key=lambda x: -x["score"])


# ---- what Claude starts from, and what he can read ---------------------------------------------------------


def course_view(conn: sqlite3.Connection, cfg: Config, course: str, now: datetime | None = None) -> dict:
    """Everything Claude needs before explaining, quizzing, or reporting where he stands in a course."""
    c = cfg.course_for(course)
    if c is None:
        raise TutorError(f"There is no course {course!r}; use its code from list_courses.")
    now = now or datetime.now(UTC)
    ts = topics(conn, cfg, c.code, now)
    flags = course_flags(conn, cfg, c.code, now=now)
    g, cur = goal(conn, c.code), current_percent(conn, c.code)
    view = {
        "course": c.code, "name": c.name,
        "standing": {"current_percent": cur, "goal": g["goal"] if g else None, "target_percent": g.get("target") if g else None},
        "topics": [{k: t[k] for k in ("topic", "stage", "next_step", "status", "misconceptions", "exams", "trail")} for t in ts],
        "flags": {k: v["line"] for k, v in flags.items()},
        "recently_solid": [t["topic"] for t in ts if t["became_solid"]],
        "how_he_learns": preferences(conn),
        "rule": STANDING_RULE,
    }
    # The groups the quiz and study commands aim by.
    for stage in STAGES:
        view[stage] = [t["topic"] for t in ts if t["stage"] == stage]
    return view


def preferences(conn: sqlite3.Connection) -> list[dict]:
    ensure(conn)
    return [{"note": r["id"], "preference": r["words"], "since": r["at"][:10]}
            for r in conn.execute("SELECT * FROM signals WHERE kind = 'preference' AND words IS NOT NULL ORDER BY at")]


def what_worked(conn: sqlite3.Connection) -> list[dict]:
    """Explanations Claude gave, and whether he got it afterward: explained well or right on the next result
    (understood the first time), or confused again (needed another try)."""
    ensure(conn)
    out = []
    for s in conn.execute("SELECT * FROM signals WHERE kind = 'explained' ORDER BY at"):
        nxt = conn.execute(
            """SELECT kind FROM signals WHERE course = ? AND topic = ? AND at > ? AND kind IN ('explained_well', 'solved', 'confused',
               'misconception', 'basic_question', 'needed_help') ORDER BY at LIMIT 1""",
            (s["course"], s["topic"], s["at"]),
        ).fetchone()
        if nxt is None:
            continue
        out.append({"topic": s["topic"], "course": s["course"], "how": s["words"] or "an explanation", "at": s["at"][:10],
                    "worked": nxt["kind"] in ("explained_well", "solved")})
    return out


def write_how_i_learn(conn: sqlite3.Connection, cfg: Config, now: datetime) -> Path | None:
    prefs, worked = preferences(conn), what_worked(conn)
    if not prefs and not worked:
        return None
    lines = ["---", "type: oso-how-i-learn", f"generated: {now.isoformat(timespec='minutes')}", "---", "",
             "# How I learn", "",
             "Generated by Oso from what you've said and from which explanations worked. Do not edit; if something here is wrong, tell Claude.", ""]
    if prefs:
        lines.append("## What you've said helps")
        lines += [f"- {p['preference']} (said {p['since']})" for p in prefs]
        lines.append("")
    if worked:
        lines.append("## What has worked")
        for w in worked[-12:]:
            lines.append(f"- {w['topic']}, {w['at']}: {w['how']}: {'understood the first time' if w['worked'] else 'needed another try'}")
        lines.append("")
    path = cfg.vault / "Oso" / "Profile" / "How I learn.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old is None or old.split("---", 2)[-1] != text.split("---", 2)[-1]:
        path.write_text(text, encoding="utf-8")
    return path
