"""File clipped notes from Clippings into their course, with no course typed, and retire the old Inbox folder.

The Web Clipper saves into `Clippings/`. On every check (and within half a minute by the folder watcher),
each clip is filed:

- a page from an online textbook (the clipper's `book` box, with its `page`) joins that book, in the course
  that already has a book by that name (a partial title is enough); for a book Oso hasn't seen, the course
  whose syllabus names it; failing that, the course its content matches; every later page follows it
- any other clip goes into the Readings folder of the course its content clearly matches, using the search
  model on the laptop (no Claude): the clip is compared with each active course's notes, readings, books,
  syllabus, and topics, and filed only when one course is close and clearly closer than the next
- a course typed in the older template's `course` box is still honored

Left in Clippings: anything that looks like a syllabus (for `/create-course` to find), clips Oso can't place
(Today.md asks which course), and clips he said belong to no course (`course: none`). Every move is logged, so
course setup can find a syllabus that was filed anyway, and he can have Claude move a clip or a whole book.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import re
import sqlite3
from datetime import UTC, datetime

from . import notes
from .config import Config, Course

log = logging.getLogger("oso.filing")

CLIPPINGS = "Clippings"


MIN_SCORE = 0.58  # how close a clip must be to a course's material to be filed there...
MARGIN = 0.06  # ...and how much closer than the next course (cautious: unclear clips are asked about)
TOP_K = 5
NO_COURSE = "none"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clip_log (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    src     TEXT NOT NULL,
    dest    TEXT NOT NULL,
    course  TEXT NOT NULL,
    how     TEXT NOT NULL,      -- typed, book, syllabus, content, or asked (moved at his word)
    at      TEXT NOT NULL
);
"""

SYLLABUS_WORDS = ("office hours", "grading", "course schedule", "course description", "learning outcomes", "learning objectives",
                  "prerequisite", "required text", "late policy", "academic integrity", "attendance policy", "instructor")


def file_clippings(cfg: Config, conn: sqlite3.Connection | None = None) -> int:
    """File every clip that can be placed. Returns how many were moved."""
    folder = cfg.vault / CLIPPINGS
    if not folder.is_dir():
        return 0
    if conn is not None:
        from . import schema

        schema.apply(conn)
    moved = 0
    profiles = None  # each course's material, loaded only if a clip needs matching by content
    for src in sorted(folder.glob("*.md")):
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, body = notes.read_front_matter(text)
        typed = str(fm.get("course") or "").strip()
        if typed.lower() == NO_COURSE:
            continue
        book = str(fm.get("book") or "").strip()
        course, how = _match(cfg, typed), "typed"
        if course is None and book:
            course, how = book_course(cfg, book), "book"
        if course is None and not book and looks_like_syllabus(fm, body):
            continue  # waits for /create-course
        if course is None:
            if profiles is None:
                profiles = course_profiles(cfg)
            course, how = content_match(cfg, profiles, f"{fm.get('title') or src.stem}\n{book}\n{body}"), "content"
        if course is None:
            continue
        dest = _file(cfg, src, fm, body, course, book)
        moved += 1
        if conn is not None:
            conn.execute("INSERT INTO clip_log (name, src, dest, course, how, at) VALUES (?, ?, ?, ?, ?, ?)",
                         (src.name, src.relative_to(cfg.vault).as_posix(), dest.relative_to(cfg.vault).as_posix(), course.code, how,
                          datetime.now(UTC).isoformat(timespec="seconds")))
    return moved


def _file(cfg: Config, src: Path, fm: dict, body: str, course: Course, book: str) -> Path:
    fm["course"] = course.code
    if book:
        # A page from an online textbook joins that book, as a source with its page number.
        folder = book_folder(cfg, course, book) or notes.safe_name(book)
        dest = _free(cfg.vault / "Courses" / course.folder / "Books" / folder / "Clipped" / src.name)
        page = str(fm.get("page") or "").strip()
        fm["type"] = "textbook"
        if page and not body.lstrip().startswith("## p."):
            body = f"## p. {page}\n\n{body.lstrip()}"
    else:
        dest = _free(cfg.vault / "Courses" / course.folder / "Readings" / src.name)
    src.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
    src.replace(dest)
    return dest


# ---- books ----------------------------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    stop = {"the", "a", "an", "of", "and", "for", "to", "in", "on", "edition", "ed", "with"}
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stop]


def _same_book(typed: str, known: str) -> bool:
    """A partial title is enough: every word typed appears in the known title (or the other way round)."""
    a, b = set(_words(typed)), set(_words(known))
    return bool(a and b) and (a <= b or b <= a)


def book_folder(cfg: Config, course: Course, book: str) -> str | None:
    """The folder name of a book this course already has, matching a typed (possibly partial) title."""
    books = cfg.vault / "Courses" / course.folder / "Books"
    if not books.is_dir():
        return None
    for d in sorted(p for p in books.iterdir() if p.is_dir()):
        if _same_book(book, d.name):
            return d.name
    return None


def book_course(cfg: Config, book: str) -> Course | None:
    """The course a book belongs to: the one already holding a book by that name, else the one whose syllabus
    names it. None when neither settles it (or more than one course could)."""
    active = [c for c in cfg.courses if not c.finished]
    have = [c for c in active if book_folder(cfg, c, book)]
    if len(have) == 1:
        return have[0]
    if len(have) > 1:
        return None
    named = [c for c in active if _syllabus_names(cfg, c, book)]
    return named[0] if len(named) == 1 else None


def _syllabus_names(cfg: Config, course: Course, book: str) -> bool:
    words = _words(book)
    if not words:
        return False
    for f in (cfg.vault / "Courses" / course.folder).glob("Syllabus*.md"):
        try:
            text = set(_words(f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
        if all(w in text for w in words):
            return True
    return False


SCRAPED = "scraped page"


def save_book_page(cfg: Config, course_code: str, book: str, page: str, text: str, url: str | None = None) -> str:
    """Save a page Claude read from an online textbook in Chrome (/scrape-page) into that course's copy of the book,
    beside clipped pages. Reading the same page again replaces the earlier reading; a page he clipped is never touched."""
    course = _match(cfg, course_code) or cfg.course_for(course_code)
    if course is None:
        return f"There is no course {course_code!r}."
    book, page, text = book.strip(), str(page).strip(), text.strip()
    if not book or not page or not text:
        return "Nothing saved: the book title, the page (or section), and the page's text are all needed."
    numbered = bool(re.fullmatch(r"\d+|[ivxlcdm]+", page, re.IGNORECASE))
    folder = book_folder(cfg, course, book) or notes.safe_name(book)
    dest = cfg.vault / "Courses" / course.folder / "Books" / folder / "Clipped" / f"{notes.safe_name(f'p. {page}' if numbered else page)}.md"
    if dest.exists():
        old, _ = notes.read_front_matter(dest.read_text(encoding="utf-8", errors="replace"))
        if old.get("source") != SCRAPED:
            dest = _free(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not text.startswith("## "):
        text = f"## {'p. ' if numbered else ''}{page}\n\n{text}"
    fm = {"type": "textbook", "course": course.code, "book": folder, "page": page, "source": SCRAPED, "url": url or None,
          "saved": datetime.now(UTC).date().isoformat()}
    dest.write_text(notes.with_front_matter({k: v for k, v in fm.items() if v is not None}, text + "\n"), encoding="utf-8")
    return f"Saved to {dest.relative_to(cfg.vault).as_posix()}."


def move_book(cfg: Config, book: str, course_code: str, conn: sqlite3.Connection | None = None) -> str:
    """Move a whole book (every page clipped so far; later pages follow) to another course."""
    to = _match(cfg, course_code) or cfg.course_for(course_code)
    if to is None:
        return f"There is no course {course_code!r}."
    for c in cfg.courses:
        folder = book_folder(cfg, c, book)
        if folder is None or c.code == to.code:
            continue
        src = cfg.vault / "Courses" / c.folder / "Books" / folder
        dest = cfg.vault / "Courses" / to.folder / "Books" / folder
        if dest.exists():
            return f"{to.name} already has a book called {folder}."
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dest)
        for md in dest.rglob("*.md"):
            fm, body = notes.read_front_matter(md.read_text(encoding="utf-8", errors="replace"))
            if fm.get("course"):
                fm["course"] = to.code
                md.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
        return f"Moved {folder} from {c.name} to {to.name}; later pages of it go there too."
    return f"No book matching {book!r} was found in another course."


# ---- matching by content ----------------------------------------------------------------------------------


def looks_like_syllabus(fm: dict, body: str) -> bool:
    title = str(fm.get("title") or "").lower()
    head = body[:6000].lower()
    headings = " ".join(line for line in head.splitlines() if line.lstrip().startswith("#"))
    if "syllabus" in title or "syllabus" in headings:
        return True
    return sum(1 for w in SYLLABUS_WORDS if w in head) >= 3


def course_profiles(cfg: Config) -> dict[str, list]:
    """Each active course's material as vectors from the search index (its notes, readings, books, syllabus),
    plus its name and topic list. Empty if the search model isn't available."""
    import numpy as np

    from . import search

    active = {c.code.lower(): c for c in cfg.courses if not c.finished}
    out: dict[str, list] = {}
    try:
        with search.connect() as idx:
            for r in idx.execute("SELECT course, vec FROM chunks WHERE vec IS NOT NULL AND course IS NOT NULL"):
                if r["course"].lower() in active:
                    out.setdefault(active[r["course"].lower()].code, []).append(np.frombuffer(r["vec"], dtype=np.float32))
    except sqlite3.Error:
        pass
    try:
        from . import db, profile

        with db.connect() as conn:
            extra = {c.code: f"{c.name}: " + ", ".join(t["name"] for t in profile.list_topics(conn, c.code)) for c in active.values()}
    except Exception:  # noqa: BLE001
        extra = {c.code: c.name for c in active.values()}
    vecs = search.embed_passages(list(extra.values()))
    if vecs is None:
        return {}
    for code, v in zip(extra, vecs):
        out.setdefault(code, []).append(np.frombuffer(v, dtype=np.float32))
    return out


def content_match(cfg: Config, profiles: dict[str, list], text: str) -> Course | None:
    """The course a clip clearly belongs to, or None. Each course scores the average closeness of its few
    closest pieces of material; filing needs a close match and a clear lead over the next course."""
    import numpy as np

    from . import search

    if not profiles:
        return None
    vecs = search.embed_passages([text[:2000]])
    if not vecs:
        return None
    v = np.frombuffer(vecs[0], dtype=np.float32)
    scores = sorted(((float(np.mean(sorted((m @ v for m in mats), reverse=True)[:TOP_K])), code) for code, mats in profiles.items()),
                    reverse=True)
    if not scores or scores[0][0] < MIN_SCORE or (len(scores) > 1 and scores[0][0] - scores[1][0] < MARGIN):
        return None
    return cfg.course_for(scores[0][1])


# ---- what the briefing says, and moving at his word ----------------------------------------------------------


def unplaced(cfg: Config) -> list[str]:
    """Clips Oso couldn't place (not syllabi, not marked as belonging to no course)."""
    folder = cfg.vault / CLIPPINGS
    out = []
    for src in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            fm, body = notes.read_front_matter(src.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if str(fm.get("course") or "").strip().lower() == NO_COURSE or looks_like_syllabus(fm, body):
            continue
        out.append(src.stem)
    return out


def recently_filed(conn: sqlite3.Connection, since: str) -> list[dict]:
    from . import schema

    schema.apply(conn)
    return [dict(r) for r in conn.execute("SELECT name, dest, course, how, at FROM clip_log WHERE at >= ? ORDER BY at", (since,))]


def file_clip(cfg: Config, name: str, course_code: str, conn: sqlite3.Connection | None = None) -> str:
    """Move a clip where he says: into a course (from Clippings, or from another course's Readings), or mark it as
    belonging to no course ("none"), which keeps it in Clippings and stops Oso asking."""
    hits = [p for p in (cfg.vault / CLIPPINGS).glob("*.md") if name.lower() in p.stem.lower()] if (cfg.vault / CLIPPINGS).is_dir() else []
    if not hits:
        hits = [p for c in cfg.courses for p in (cfg.vault / "Courses" / c.folder / "Readings").glob("*.md") if name.lower() in p.stem.lower()]
    if not hits:
        return f"No clip called {name!r} in Clippings or a course's Readings."
    if len(hits) > 1:
        return "More than one clip matches: " + "; ".join(p.stem for p in hits[:6]) + ". Say which."
    src = hits[0]
    fm, body = notes.read_front_matter(src.read_text(encoding="utf-8", errors="replace"))
    if course_code.strip().lower() == NO_COURSE:
        fm["course"] = NO_COURSE
        dest = src if src.parent.name == CLIPPINGS else _free(cfg.vault / CLIPPINGS / src.name)
        src.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
        if dest != src:
            src.replace(dest)
        return f"{src.stem} stays in Clippings, not tied to a course."
    course = _match(cfg, course_code) or cfg.course_for(course_code)
    if course is None:
        return f"There is no course {course_code!r}."
    dest = _file(cfg, src, fm, body, course, str(fm.get("book") or "").strip() if src.parent.name == CLIPPINGS else "")
    if conn is not None:
        from . import schema

        schema.apply(conn)
        conn.execute("INSERT INTO clip_log (name, src, dest, course, how, at) VALUES (?, ?, ?, ?, ?, ?)",
                     (src.name, src.relative_to(cfg.vault).as_posix(), dest.relative_to(cfg.vault).as_posix(), course.code, "asked",
                      datetime.now(UTC).isoformat(timespec="seconds")))
    return f"Filed {src.stem} in {course.name}."


def retire_inbox(cfg: Config) -> int:
    """Earlier versions kept clips, the alert log, and course-less scans in `Inbox/`. Move the clips to
    Clippings and the log to Oso, then remove the folder if nothing else is left in it. Course-less
    scans are not moved: scans outside a course are ignored. Returns the number of files moved."""
    inbox = cfg.vault / "Inbox"
    if not inbox.is_dir():
        return 0
    moved = 0
    alerts = inbox / "Alerts.md"
    if alerts.is_file():
        dest = cfg.vault / "Oso" / "Alerts.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.write_text(dest.read_text(encoding="utf-8") + "\n" + _lines_only(alerts), encoding="utf-8")
            alerts.unlink()
        else:
            alerts.replace(dest)
        moved += 1
    for src in sorted(inbox.glob("*")):
        if src.is_file():
            src.replace(_free(cfg.vault / CLIPPINGS / src.name))
            moved += 1
    for d in sorted((p for p in inbox.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    if not any(inbox.iterdir()):
        shutil.rmtree(inbox, ignore_errors=True)
    return moved


def _lines_only(alerts: Path) -> str:
    return "\n".join(line for line in alerts.read_text(encoding="utf-8").splitlines() if line.startswith("- "))


def _free(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 2
    candidate = dest
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return candidate


def _match(cfg: Config, value) -> Course | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    return next((c for c in cfg.courses if v == c.folder.lower()), None) or cfg.resolve(value)
