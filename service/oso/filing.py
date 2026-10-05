"""File clipped notes from Inbox into their course folder.

The Web Clipper saves into `Inbox/` with a `course` property. When the student fills that property in
(the course code, or the course's name or folder), the next sync moves the note into
`Courses/<folder>/Readings/`. Notes without a course stay in Inbox.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import notes
from .config import Config, Course

log = logging.getLogger("oso.filing")


def file_inbox(cfg: Config) -> int:
    inbox = cfg.vault / "Inbox"
    if not inbox.is_dir():
        return 0
    moved = 0
    for src in sorted(inbox.glob("*.md")):
        if src.name in ("Alerts.md",):
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, _ = notes.read_front_matter(text)
        course = _match(cfg, fm.get("course"))
        if course is None:
            continue
        dest_dir = cfg.vault / "Courses" / course.folder / "Readings"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        n = 2
        while dest.exists():
            dest = dest_dir / f"{src.stem} ({n}){src.suffix}"
            n += 1
        if fm.get("course") != course.code:
            fm["course"] = course.code
            _, body = notes.read_front_matter(text)
            src.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
        src.replace(dest)
        moved += 1
    return moved


def _match(cfg: Config, value) -> Course | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    for c in cfg.courses:
        if v in (c.code.lower(), c.name.lower(), c.folder.lower()):
            return c
    return None
