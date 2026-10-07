"""Courses: where they live, which ones are current, and which earlier ones they build on.

Each course lives under its term, `Courses/<term>/<name>` (for example `Courses/2026 Fall/Calculus II`),
and stays there for good: moving folders would break links between notes and make Drive re-sync them.
When a semester ends a course is marked finished instead of archived. A finished course drops out of
`Today.md`, the dashboard, alerts, and default search, but its notes are still searched when it is named,
or when a later course lists it as related (Calculus III related to Calculus II).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta

from . import config as cfgmod
from . import db
from .config import Config, Course

SUBFOLDERS = ("Lectures", "Homework", "Readings", "Notes", "Exams", "Handwriting")
_TERM = re.compile(r"^(19|20)\d\d (Spring|Summer|Fall|Winter)$")


def term_for(d: date) -> str:
    """The usual US academic term a date falls in."""
    season = "Spring" if d.month <= 5 else "Summer" if d.month <= 7 else "Fall"
    return f"{d.year} {season}"


def check_term(term: str) -> str:
    t = " ".join(term.split()).title()
    if not _TERM.match(t):
        raise ValueError(f"term should look like '2026 Fall' or '2027 Spring', not {term!r}")
    return t


def register(cfg: Config, code: str, name: str, term: str | None = None, related: list[str] | None = None,
             ai_policy: str | None = None, folder: str | None = None) -> Course:
    """Add a course, or update one set up before (its folder never moves once created)."""
    existing = cfg.course_for(code)
    term = check_term(term) if term else (existing.term if existing else None)
    if existing:
        course = existing
        course.name = name
        course.term = term
        if related is not None:
            course.related = _codes(cfg, related, code)
    else:
        course = Course(code=code, name=name, folder=folder or (f"{term}/{name}" if term else name), term=term,
                        related=_codes(cfg, related or [], code))
        cfg.courses.append(course)
    cfgmod.save(cfg)
    with db.connect() as conn:
        db.upsert_course(conn, code, name, course.folder, ai_policy)
    for sub in SUBFOLDERS:
        (cfg.vault / "Courses" / course.folder / sub).mkdir(parents=True, exist_ok=True)
    return course


def update(cfg: Config, code: str, finished: bool | None = None, related: list[str] | None = None,
           add_site: str | None = None, remove_site: str | None = None) -> Course:
    course = cfg.course_for(code)
    if course is None:
        raise ValueError(f"no course {code!r}")
    if finished is not None:
        course.finished = finished
    if related is not None:
        course.related = _codes(cfg, related, code)
    if add_site:
        from .sites import normalize

        url = normalize(add_site)
        if url not in course.sites:
            course.sites.append(url)
    if remove_site:
        course.sites = [u for u in course.sites if u.rstrip("/") != remove_site.strip().rstrip("/") and remove_site.strip() not in u]
    cfgmod.save(cfg)
    return course


def _codes(cfg: Config, refs: list[str], own: str) -> list[str]:
    """Course codes for references given as codes or names; unknown ones are an error."""
    out = []
    for ref in refs:
        c = cfg.course_for(ref) or next((x for x in cfg.courses if ref.lower() in (x.name.lower(), x.folder_name.lower())), None)
        if c is None:
            raise ValueError(f"no course {ref!r} to relate to")
        if c.code.lower() != own.lower() and c.code not in out:
            out.append(c.code)
    return out


def describe(cfg: Config) -> list[dict]:
    return [
        {"code": c.code, "name": c.name, "term": c.term, "folder": f"Courses/{c.folder}", "finished": c.finished, "related": c.related,
         "sites": c.sites}
        for c in sorted(cfg.courses, key=lambda c: (c.finished, c.term or "", c.name))
    ]


def looks_finished(conn: sqlite3.Connection, cfg: Config, now: datetime, quiet_days: int = 14) -> list[Course]:
    """Active courses whose every dated item is more than `quiet_days` in the past: likely over."""
    out = []
    cutoff = (now - timedelta(days=quiet_days)).isoformat(timespec="minutes")
    for c in cfg.courses:
        if c.finished:
            continue
        row = conn.execute(
            """SELECT MAX(COALESCE(user_due_at, due_at)) AS last, COUNT(*) AS n FROM items
               WHERE deleted_at IS NULL AND merged_into IS NULL AND COALESCE(user_course, course_code) = ?
               AND COALESCE(user_due_at, due_at) IS NOT NULL""",
            (c.code,),
        ).fetchone()
        if row["n"] and row["last"] < cutoff:
            out.append(c)
    return out
