"""MCP server over the Oso database and vault, used by the skills in Cowork and Claude Code.

Tool descriptions are kept short on purpose: every one of them sits in Claude's context for every conversation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from mcp.server.mcpserver import MCPServer

from . import config as cfgmod
from . import db
from .db import EFFECTIVE

mcp = MCPServer("oso")

STATUSES = ("not_started", "started", "done")
KINDS = ("assignment", "quiz", "exam", "reading", "event")


def _cfg() -> cfgmod.Config:
    return cfgmod.load()


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


def _vault_file(cfg: cfgmod.Config, path: str):
    target = (cfg.vault / path).resolve()
    if cfg.vault.resolve() not in target.parents:
        raise ValueError("path must be inside the vault")
    return target


# ---- courses and deadlines ---------------------------------------------------------------------


@mcp.tool()
def list_courses() -> list[dict]:
    """Courses with code, term, vault folder, finished flag, related earlier courses, and AI policy."""
    from . import courses

    with db.connect() as conn:
        policy = {r["code"]: r["ai_policy"] for r in conn.execute("SELECT code, ai_policy FROM courses")}
    return [{**c, "ai_policy": policy.get(c["code"])} for c in courses.describe(_cfg())]


@mcp.tool()
def add_course(code: str, name: str, term: str | None = None, related: list[str] | None = None, ai_policy: str | None = None) -> dict:
    """Register or update a course: code as Canvas labels it, term like "2026 Fall", related = earlier courses it builds on."""
    from . import courses

    c = courses.register(_cfg(), code, name, term=term, related=related, ai_policy=ai_policy)
    return {"code": c.code, "name": c.name, "term": c.term, "folder": f"Courses/{c.folder}", "related": c.related}


@mcp.tool()
def update_course(code: str, finished: bool | None = None, related: list[str] | None = None,
                  add_site: str | None = None, remove_site: str | None = None) -> dict:
    """Mark a course finished (or current again), set the earlier courses it builds on, or add/remove an instructor web page Oso follows for new materials."""
    from . import courses

    c = courses.update(_cfg(), code, finished=finished, related=related, add_site=add_site, remove_site=remove_site)
    return {"code": c.code, "finished": c.finished, "related": c.related, "sites": c.sites}


@mcp.tool()
def list_deadlines(days: int = 14, course: str | None = None, include_done: bool = False) -> list[dict]:
    """Open items due within `days` (plus overdue), soonest first."""
    cfg = _cfg()
    now = datetime.now(cfg.tz)
    horizon = (now + timedelta(days=days)).isoformat(timespec="minutes")
    sql = f"""SELECT id, kind, source, url, {EFFECTIVE} FROM items
              WHERE deleted_at IS NULL AND merged_into IS NULL AND (due_at IS NULL OR COALESCE(user_due_at, due_at) <= ?)"""
    params: list = [horizon]
    if course:
        sql += " AND COALESCE(user_course, course_code) = ?"
        params.append(course)
    sql += " ORDER BY COALESCE(user_due_at, due_at)"
    with db.connect() as conn:
        rows = [_row(r) for r in conn.execute(sql, params)]
    if not course:
        rows = [r for r in rows if cfg.is_active(r["course_code"])]
    if not include_done:
        rows = [r for r in rows if r["status"] != "done"]
    return rows


@mcp.tool()
def get_item(item_id: int) -> dict:
    """One item in full, with description and source."""
    with db.connect() as conn:
        r = conn.execute(f"SELECT *, {EFFECTIVE} FROM items WHERE id = ?", (item_id,)).fetchone()
    if r is None:
        raise ValueError(f"No item {item_id}")
    return _row(r)


@mcp.tool()
def add_item(course: str, title: str, kind: str, due_at: str | None = None, weight: float | None = None, description: str | None = None) -> dict:
    """Add a confirmed syllabus item. kind: assignment|quiz|exam|reading|event; due_at ISO."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    cfg = _cfg()
    due = _parse_due(due_at, cfg) if due_at else None
    ts = db.now_iso()
    ext = f"{course}:{kind}:{title}:{due[:10] if due else ''}"
    with db.connect() as conn:
        cur = conn.execute(
            """INSERT INTO items (source, external_id, course_code, kind, title, due_at, all_day, description, weight, first_seen, last_seen)
               VALUES ('syllabus', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, external_id) DO UPDATE SET due_at = excluded.due_at, weight = excluded.weight,
                 description = excluded.description, last_seen = excluded.last_seen, deleted_at = NULL""",
            (ext, course, kind, title, due, int(bool(due) and len(due_at or "") <= 10), description, weight, ts, ts),
        )
        item_id = cur.lastrowid
    return {"id": item_id, "course": course, "title": title, "kind": kind, "due_at": due, "weight": weight}


@mcp.tool()
def update_status(item_id: int, status: str) -> dict:
    """Set an item to not_started, started, or done."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_status = ? WHERE id = ?", (status, item_id))
    return {"id": item_id, "status": status}


@mcp.tool()
def set_due_date(item_id: int, due_at: str | None) -> dict:
    """Override an item's due date (ISO), or null to use the source's."""
    cfg = _cfg()
    due = _parse_due(due_at, cfg) if due_at else None
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_due_at = ? WHERE id = ?", (due, item_id))
    return {"id": item_id, "due_at": due}


@mcp.tool()
def set_weight(item_id: int, weight: float | None) -> dict:
    """Set the percent of the course grade an item's category is worth."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET user_weight = ? WHERE id = ?", (weight, item_id))
    return {"id": item_id, "weight": weight}


@mcp.tool()
def record_grade(item_id: int, points: float, max_points: float) -> dict:
    """Record a received grade."""
    with db.connect() as conn:
        conn.execute("UPDATE items SET grade_points = ?, grade_max = ?, user_status = 'done' WHERE id = ?", (points, max_points, item_id))
    return {"id": item_id, "points": points, "max_points": max_points}


@mcp.tool()
def grade_summary(course: str) -> dict:
    """Standing in a course: percent so far, weight graded and remaining, per category."""
    from . import grades

    with db.connect() as conn:
        return grades.summary(conn, course)


@mcp.tool()
def what_if(course: str, target_percent: float) -> dict:
    """Average needed on remaining work to finish at target_percent."""
    from . import grades

    with db.connect() as conn:
        return grades.what_if(conn, course, target_percent)


# ---- briefing, alerts, health ------------------------------------------------------------------


@mcp.tool()
def today() -> str:
    """Today.md: due today and this week, exams, changes, connection health."""
    cfg = _cfg()
    path = cfg.vault / "Today.md"
    if not path.exists():
        return "Today.md has not been generated yet. Run 'oso sync'."
    return path.read_text(encoding="utf-8")


@mcp.tool()
def pending_alerts() -> list[dict]:
    """Urgent changes not yet delivered, with deliver_after during quiet hours."""
    from . import alerts

    cfg = _cfg()
    with db.connect() as conn:
        return alerts.pending(conn, cfg, datetime.now(cfg.tz))


@mcp.tool()
def mark_alert_reported(alert_id: int) -> dict:
    """Mark an alert as delivered."""
    from . import alerts

    with db.connect() as conn:
        alerts.mark_reported(conn, alert_id)
    return {"alert_id": alert_id, "reported": True}


@mcp.tool()
def health() -> list[dict]:
    """Last sync and last error per source."""
    with db.connect() as conn:
        return [_row(r) for r in db.connector_health(conn)]


# ---- looking after Oso (the same actions as the buttons in the Oso window) -----------------------


@mcp.tool()
def open_settings() -> str:
    """Open the Oso window (status and settings) on the student's computer, or bring it to the front if it is already open."""
    from . import actions

    return actions.open_settings()


@mcp.tool()
def oso_status() -> list[dict]:
    """Oso's status, one plain line each: {status: ok|warn|fail, text, action (what fixes it, if anything)}."""
    from . import actions

    return actions.status()


@mcp.tool()
def run_health_check(fix: bool = False) -> str:
    """Check Oso's health; with fix, repair what can be repaired (schedule, watcher, folders). Returns plain sentences."""
    from . import actions

    return actions.health_check(fix=fix)


@mcp.tool()
def sync_now() -> str:
    """Start a full check of every source now, in the background."""
    from . import actions

    return actions.sync_now()


@mcp.tool()
def update_oso() -> str:
    """Install the newest Oso on the student's update channel. On Windows a visible update window does the install and this connection restarts."""
    from . import actions

    return actions.update_oso()


@mcp.tool()
def backup_now() -> str:
    """Back up the vault and Oso's records now, to the backup folder in settings."""
    from . import actions

    return actions.backup_now()


# ---- his week: school email, GroupMe, and the Oso calendar --------------------------------------


@mcp.tool()
def schedule(days: int = 7) -> dict:
    """His schedule for the coming days (the Oso calendar, plus events from school email and GroupMe), the actions he
    needs to take, and conflicts worth raising. Each event has `happening` (Oso's id) and/or `event_id` (the calendar's)."""
    from . import happenings

    cfg = _cfg()
    now = datetime.now(cfg.tz)
    with db.connect() as conn:
        return {
            "schedule": happenings.schedule(conn, cfg, now, days),
            "to_do": [h for h in happenings.upcoming(conn, cfg, now, max(days, 14)) if h["kind"] == "action"],
            "heads_up": happenings.conflicts(conn, cfg, now, days),
        }


@mcp.tool()
def add_to_calendar(title: str, start: str, end: str | None = None, location: str | None = None, notes: str | None = None,
                    kind: str = "event") -> dict:
    """Add an event (or, with kind "action", something he needs to do by a date) to his schedule and the Oso calendar,
    when he asks ("add Saturday's tailgate, noon at the stadium"). start/end: local YYYY-MM-DDTHH:MM, or YYYY-MM-DD for all day."""
    from . import happenings

    cfg = _cfg()
    now = datetime.now(cfg.tz)
    with db.connect() as conn:
        hid = happenings.add(conn, "action" if kind == "action" else "event", title, start[:16], ends_at=end[:16] if end else None,
                             all_day=len(start) <= 10, location=location, source="chat", note=notes)
        if hid is None:
            return {"added": False, "note": "That is already on his schedule."}
        conn.commit()
        problem = happenings.push(conn, cfg, now) if kind != "action" else None
    return {"added": True, "happening": hid, **({"note": problem} if problem else {})}


@mcp.tool()
def change_calendar(happening: int | None = None, event_id: str | None = None, cancel: bool = False, start: str | None = None,
                    end: str | None = None, title: str | None = None, location: str | None = None) -> dict:
    """Move, rename, relocate, or remove something on his schedule, only when he asks. Pass `happening` for anything Oso
    keeps (from email, GroupMe, or added in chat), or `event_id` for an event he put on the Oso calendar himself."""
    from . import happenings

    cfg = _cfg()
    now = datetime.now(cfg.tz)
    with db.connect() as conn:
        if happening is not None:
            if not happenings.change(conn, happening, now, canceled=cancel, starts_at=start[:16] if start else None,
                                     ends_at=end[:16] if end else None, location=location, title=title,
                                     note="Canceled at his request." if cancel else "Changed at his request."):
                return {"changed": False, "note": "No such item on his schedule."}
            conn.commit()
            problem = happenings.push(conn, cfg, now)
            return {"changed": True, **({"note": problem} if problem else {})}
        if event_id:
            return {"changed": True, "note": happenings.change_calendar_event(conn, cfg, now, event_id, cancel=cancel, start=start,
                                                                              end=end, title=title, location=location)}
    return {"changed": False, "note": "Say which item: a happening id or an event_id from `schedule`."}


@mcp.tool()
def mute(group: str | None = None, sender: str | None = None, unmute: bool = False) -> dict:
    """Stop (or, with unmute, resume) reading a GroupMe group (by name) or an email sender (an address, an @domain, or a
    mailing list). Lists the groups and muted senders."""
    from . import groupme

    cfg = _cfg()
    with db.connect() as conn:
        groups = groupme.groups(conn)
    note = ""
    if group:
        match = next((g for g in groups if g["name"].lower() == group.strip().lower()), None) or \
            next((g for g in groups if group.strip().lower() in g["name"].lower()), None)
        if match is None:
            note = f"No GroupMe group called {group!r}."
        else:
            ids = [x for x in cfg.muted_groups if x != match["id"]]
            cfg.muted_groups = ids if unmute else ids + [match["id"]]
            note = f"{'Reading' if unmute else 'No longer reading'} {match['name']}."
    if sender:
        s = sender.strip().lower()
        rest = [x for x in cfg.muted_senders if x.lower() != s]
        cfg.muted_senders = rest if unmute else rest + [s]
        note += f" {'Reading' if unmute else 'No longer reading'} email from {s}."
    if group or sender:
        cfgmod.save(cfg)
    muted = set(cfg.muted_groups)
    return {"note": note.strip(), "groups": [{"name": g["name"], "muted": g["id"] in muted} for g in groups],
            "muted_senders": cfg.muted_senders}


# ---- learner profile ---------------------------------------------------------------------------


@mcp.tool()
def start_quiz(course: str, questions: list[dict], requested: str | None = None, sources: list[str] | None = None,
               retake_of: int | None = None, window: bool = True) -> dict:
    """Record a quiz and open it in the quiz window on the student's computer. questions: [{number, topic, theme, type: multiple_choice|short_answer|worked_problem|conceptual, difficulty: easy|medium|hard, question, source, choices (multiple choice: a list of the answer texts, without letters), answer (the correct choice's letter)}]. Returns quiz_id."""
    from . import profile, quizwin

    with db.connect() as conn:
        quiz_id = profile.start_quiz(conn, _cfg(), course, questions, requested, sources, retake_of, window=window)
    if not window:
        return {"quiz_id": quiz_id}
    try:
        quizwin.launch(quiz_id)
    except Exception:  # noqa: BLE001
        return {"quiz_id": quiz_id, "window": "could not open; ask the student to run: oso quiz " + str(quiz_id)}
    return {"quiz_id": quiz_id, "window": "opened"}


@mcp.tool()
def quiz_responses(quiz_id: int) -> dict:
    """A window quiz's answers for grading: typed responses, timing, multiple choice already graded, and written-work page images to match by their corner labels."""
    from . import profile

    with db.connect() as conn:
        return profile.grading_view(conn, _cfg(), quiz_id)


@mcp.tool()
def record_answers(quiz_id: int, answers: list[dict]) -> dict:
    """Record graded answers: [{number, result: right|partly_right|wrong|skipped, mistake: concept_gap|calculation_slip|misread_question|incomplete (if not right), hint: bool}]. Re-answering counts as another attempt."""
    from . import profile

    with db.connect() as conn:
        return profile.record_answers(conn, quiz_id, answers)


@mcp.tool()
def finish_quiz(quiz_id: int) -> dict:
    """Close a quiz after grading; returns its score and per-question results."""
    from . import profile

    with db.connect() as conn:
        return profile.finish_quiz(conn, quiz_id)


@mcp.tool()
def show_quiz(quiz_id: int) -> str:
    """Open a past quiz on his computer in the quiz window, exactly as he took it, read-only, with his answers, the right
    answers, his grades, and your notes. Find the id with `recent_quizzes`."""
    from . import actions

    return actions.open_quiz(quiz_id)


@mcp.tool()
def get_profile(course: str) -> dict:
    """Where he stands in a course, computed by Oso from evidence: each topic's stage, next step, status line, open
    misconceptions, and trail; his grade and goal; honesty flags; how he learns. Report the status lines as they are,
    never upgraded. Be a direct, honest tutor: name the evidence for anything positive, lead with gaps, no unearned praise."""
    from . import tutor

    with db.connect() as conn:
        return tutor.course_view(conn, _cfg(), course)


@mcp.tool()
def note_signal(kind: str, course: str | None = None, topic: str | None = None, words: str | None = None,
                belief: str | None = None, misconception: int | None = None, target_percent: float | None = None) -> dict:
    """Quietly note what he shows in a study conversation, as it happens, never announced. kind: confused, misconception
    (belief = the wrong idea itself), basic_question, explained_well (explained it correctly in his own words; pass
    misconception to close one), solved / needed_help (worked a problem in chat), explained (you explained it; words =
    how), preference (how he learns), goal (words as he said it, target_percent if a grade). words: his words where they show it."""
    from . import tutor

    with db.connect() as conn:
        return tutor.note_signal(conn, _cfg(), kind, course, topic, words, belief, misconception, target_percent)


@mcp.tool()
def correct_note(note: int | None = None, misconception: int | None = None, reopen: bool = False) -> str:
    """When he says a conversation note or misconception is wrong: remove the note, or remove or reopen the misconception."""
    from . import tutor

    with db.connect() as conn:
        return tutor.forget(conn, note, misconception, reopen)


@mcp.tool()
def study_attention() -> list[dict]:
    """Which courses need study time most, with reasons (topics needing focus, the next exam, grade against his goal,
    upcoming work) and a suggested share of study time."""
    from . import tutor

    with db.connect() as conn:
        return tutor.attention(conn, _cfg())


@mcp.tool()
def delete_quiz(quiz_id: int) -> str:
    """Delete a quiz completely (a test run, or one given by mistake) after the student confirms; its results stop counting anywhere."""
    from . import profile

    with db.connect() as conn:
        return profile.delete_quiz(conn, _cfg(), quiz_id)


@mcp.tool()
def canvas_info(course: str, what: str = "summary") -> dict:
    """What Oso read from Canvas for a course. what: summary (grade, recent scores, missing and late work) | assignments (each with score and topics) | comments (instructor feedback) | untagged (assignments awaiting topics)."""
    from . import canvas_store

    with db.connect() as conn:
        return canvas_store.info(conn, _cfg(), course, what)


@mcp.tool()
def tag_assignments(tags: list[dict]) -> dict:
    """Store the syllabus topics each Canvas assignment covers: [{canvas_id, topics: [...]}]; an empty list means it fits none."""
    from . import canvas_store

    with db.connect() as conn:
        return {"tagged": canvas_store.tag(conn, _cfg(), tags)}


@mcp.tool()
def correct_result(quiz_id: int | None = None, number: int | None = None, check_id: int | None = None,
                   result: str | None = None, mistake: str | None = None, remove: bool = False, reason: str | None = None) -> str:
    """Fix a recorded result: a quiz question (quiz_id + number) or a check (check_id); new result and mistake kind, or
    remove. Changing a grade needs `reason`: the stored criterion that supports it, or what was recorded wrong. Arguing
    alone ("I meant that") is not a reason."""
    from . import profile

    with db.connect() as conn:
        return profile.correct(conn, quiz_id, number, check_id, result, mistake, remove, reason)


@mcp.tool()
def practice_habits() -> dict:
    """Practice-habit numbers from quiz and check results: lead time before exams, follow-through on missed topics, score trends, practice share per course, pace. enough_data says whether there is enough to describe."""
    from . import habits

    with db.connect() as conn:
        return habits.compute(conn, _cfg())


@mcp.tool()
def save_habits_summary(narrative: str) -> dict:
    """Save the weekly practice-habits note (your short narrative; Oso appends the numbers) to Oso/Profile/Habits.md."""
    from . import habits

    cfg = _cfg()
    with db.connect() as conn:
        h = habits.compute(conn, cfg)
    return {"path": habits.save(cfg, narrative, h)}


@mcp.tool()
def course_topics(course: str, topics: list[dict] | None = None) -> list[dict]:
    """A course's topic list. Pass topics [{name, week, exams: [exam names]}] to set them from the syllabus (topics found later are kept)."""
    from . import profile

    with db.connect() as conn:
        if topics is not None:
            return profile.set_topics(conn, _cfg(), course, topics)
        return profile.list_topics(conn, course)


@mcp.tool()
def record_check(course: str, topic: str, correct: bool, theme: str | None = None, mistake: str | None = None,
                 mistake_at: str | None = None, hints: int = 0, full_solution: bool = False) -> dict:
    """Record a check of the student's own work: topic, whether it was right as submitted, the first mistake's kind (concept_gap|calculation_slip|misread_question|incomplete) and where, hints given, full solution shown."""
    from . import profile

    with db.connect() as conn:
        return profile.record_check(conn, _cfg(), course, topic, correct, theme, mistake, mistake_at, hints, full_solution)


@mcp.tool()
def recent_quizzes(course: str | None = None, limit: int = 10) -> list[dict]:
    """Recent quizzes with topics, status, and score (to find one to retake)."""
    from . import profile

    with db.connect() as conn:
        return profile.recent_quizzes(conn, course, limit)


# ---- notes -------------------------------------------------------------------------------------


@mcp.tool()
def search_notes(query: str, course: str | None = None, limit: int = 8, source: str | None = None) -> list[dict]:
    """Best-matching sections of the student's notes and materials, by meaning and exact words. source: "book" (textbooks only; headings are "p. N") | "notes" (everything else) | omit for both. With a course: it and its related earlier courses."""
    from . import search

    return search.query(_cfg(), query, course=course, limit=limit, source=source)


@mcp.tool()
def book_page(book: str, page: str) -> dict:
    """One textbook page: its text, whether it was read poorly, and its page image path (look at the image for equations, tables, figures)."""
    from . import books

    return books.page(_cfg(), book, page)


@mcp.tool()
def save_page_reading(book: str, page: str, text: str) -> str:
    """Save your reading of a textbook page that was read poorly (from its image), so it never needs reading again."""
    from . import books

    with db.connect() as conn:
        return books.save_page_reading(_cfg(), book, page, text, conn)


@mcp.tool()
def read_note(path: str, start: int = 0, max_chars: int | None = None) -> dict:
    """Read a vault file (path relative to the vault) from `start`. Long files are capped (see `truncated`, `next_start`); prefer read_section."""
    cfg = _cfg()
    text = _vault_file(cfg, path).read_text(encoding="utf-8", errors="replace")
    cap = cfg.read_cap_chars if max_chars is None else max_chars
    if cap and cap > 0 and len(text) - start > cap:
        chunk = text[start:start + cap]
        return {"path": path, "text": chunk, "truncated": True, "next_start": start + cap, "total_chars": len(text)}
    return {"path": path, "text": text[start:], "truncated": False, "next_start": None, "total_chars": len(text)}


@mcp.tool()
def read_section(path: str, heading: str) -> dict:
    """Read just the section under `heading` of a vault file."""
    from .notes import read_front_matter, split_sections

    cfg = _cfg()
    text = _vault_file(cfg, path).read_text(encoding="utf-8", errors="replace")
    _, body = read_front_matter(text)
    want = heading.strip().lower()
    parts = [t for h, t in split_sections(body, max_chars=10**9) if h.strip().lower() == want]
    if not parts:
        return {"path": path, "heading": heading, "text": "", "found": False}
    return {"path": path, "heading": heading, "text": "\n\n".join(parts), "found": True}


@mcp.tool()
def list_notes(folder: str = "Clippings", limit: int = 50) -> list[dict]:
    """Files under a vault folder (e.g. Clippings, Courses/Physics/Notes), newest first, with title and type."""
    from .notes import read_front_matter

    cfg = _cfg()
    root = cfg.vault.resolve() if folder.strip("/. ") == "" else _vault_file(cfg, folder)
    if not root.is_dir():
        return []
    files = [f for f in root.rglob("*") if f.is_file() and not any(p.startswith(".") or p == "pages" for p in f.relative_to(root).parts)]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        fm = {}
        if f.suffix.lower() == ".md":
            fm, _ = read_front_matter(f.read_text(encoding="utf-8", errors="replace")[:4000])
        out.append({
            "path": f.relative_to(cfg.vault.resolve()).as_posix(),
            "modified": datetime.fromtimestamp(f.stat().st_mtime, cfg.tz).isoformat(timespec="minutes"),
            "title": fm.get("title"),
            "type": fm.get("type"),
            "course": fm.get("course"),
        })
    return out


@mcp.tool()
def file_syllabus(course: str, path: str) -> dict:
    """Move a syllabus (vault path, usually in Clippings) to Courses/<folder>/Syllabus and tag it with the course."""
    from .notes import read_front_matter, with_front_matter

    cfg = _cfg()
    c = cfg.course_for(course)
    if c is None:
        raise ValueError(f"no course {course!r}; call add_course first")
    src = _vault_file(cfg, path)
    if not src.is_file():
        raise ValueError(f"{path} is not a file in the vault")
    dest = cfg.vault / "Courses" / c.folder / f"Syllabus{src.suffix.lower()}"
    if dest.resolve() == src:
        return {"path": dest.relative_to(cfg.vault).as_posix()}
    n = 2
    while dest.exists():
        dest = dest.with_name(f"Syllabus ({n}){src.suffix.lower()}")
        n += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".md":
        fm, body = read_front_matter(src.read_text(encoding="utf-8", errors="replace"))
        fm.update({"type": "syllabus", "course": c.code})
        src.write_text(with_front_matter(fm, body), encoding="utf-8")
    src.replace(dest)
    return {"path": dest.relative_to(cfg.vault).as_posix()}


@mcp.tool()
def skill_instructions(name: str) -> str:
    """The instructions for an Oso command (the student's copy in Oso/Skills)."""
    from . import skillsync

    return skillsync.instructions(_cfg(), name)


@mcp.tool()
def resolve_skill(name: str | None = None, choice: str | None = None, text: str | None = None) -> list[dict] | str:
    """No arguments: list commands whose new Oso version clashes with the student's edits. With name and choice (mine, oso, combined + text): settle one. Choice default (name optional): restore Oso's version."""
    from . import skillsync

    cfg = _cfg()
    if choice == "default":
        return skillsync.reset(cfg, [name] if name else None)
    if not name:
        return skillsync.describe(cfg)
    return skillsync.resolve(cfg, name, choice or "", text)


@mcp.tool()
def vault_path() -> str:
    """Absolute path of the vault."""
    return str(_cfg().vault)


# ---- handwriting -------------------------------------------------------------------------------


@mcp.tool()
def pending_pages(limit: int = 20) -> list[dict]:
    """Page images waiting for transcription, with notebook and course."""
    from . import handwriting

    with db.connect() as conn:
        return handwriting.pending(conn, limit=limit)


@mcp.tool()
def mark_transcribed(page_path: str, note_path: str, confidence: float) -> dict:
    """Record a transcribed page and its confidence (0 to 1)."""
    from . import handwriting

    with db.connect() as conn:
        handwriting.mark(conn, page_path, note_path, confidence)
    return {"page": page_path, "note": note_path, "confidence": confidence}


def _parse_due(value: str, cfg: cfgmod.Config) -> str:
    dt = datetime.fromisoformat(value)
    if len(value) <= 10:
        dt = dt.replace(hour=23, minute=59)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=cfg.tz)
    return dt.isoformat(timespec="minutes")


def _warm_search_model() -> None:
    """Load the search model in the background so the first question does not wait for it."""
    import threading

    from . import search

    threading.Thread(target=search._embedder, daemon=True).start()


def main() -> None:
    _warm_search_model()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
