"""File clipped notes from Clippings into their course folder, and retire the old Inbox folder.

The Web Clipper saves into `Clippings/` (its default) with a `course` property when the Oso template is
used. When the student fills that property in (the course code, or the course's name or folder), the next
sync moves the note into `Courses/<folder>/Readings/`. Notes without a course stay in Clippings.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from . import notes
from .config import Config, Course

log = logging.getLogger("oso.filing")

CLIPPINGS = "Clippings"


def file_clippings(cfg: Config) -> int:
    folder = cfg.vault / CLIPPINGS
    if not folder.is_dir():
        return 0
    moved = 0
    for src in sorted(folder.glob("*.md")):
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, body = notes.read_front_matter(text)
        course = _match(cfg, fm.get("course"))
        if course is None:
            continue
        dest = _free(cfg.vault / "Courses" / course.folder / "Readings" / src.name)
        if fm.get("course") != course.code:
            fm["course"] = course.code
            src.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
        src.replace(dest)
        moved += 1
    return moved


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
    for c in cfg.courses:
        if v in (c.code.lower(), c.name.lower(), c.folder.lower(), c.folder_name.lower()):
            return c
    return None
