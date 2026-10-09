"""Every note Oso writes into the vault goes through here, so that one rule is kept in one place: a note the
student wrote, or an Oso note he has since edited, is never overwritten.

Each note Oso writes carries `oso: <hash>` in its front matter, the hash of the body as written. On the next
write the file is Oso's if the marker matches the body; edited by him if it does not; his own if there is no
marker at all. Notes written before this marker existed are recognized by the `legacy` test a caller passes
(for example "front matter says type: textbook"), and get the marker on their first rewrite.

Writes are atomic (a temporary file renamed into place), so Google Drive never carries a half-written note.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Callable

from . import notes

log = logging.getLogger("oso.vault")

MARK = "oso"
# Folders no reader, converter, or watcher looks inside: page images, Obsidian's own, and what Oso keeps private.
SKIP_PARTS = frozenset({"pages", ".obsidian", ".trash", "Quizzes", "Handwriting"})
# Folders the service fills by itself; a change inside them is never the student's.
GENERATED_PARTS = frozenset({"Canvas", "Announcements", "Web"})


def body_hash(body: str) -> str:
    return hashlib.sha256(body.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:16]


def ownership(path: Path, legacy: Callable[[dict], bool] | None = None) -> str:
    """'missing', 'ours' (Oso wrote it and he has not touched it), 'edited' (Oso wrote it, he changed it), or
    'theirs' (his own note, or one from before the marker that `legacy` does not recognize)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "theirs"  # unreadable: treat as his, and leave it alone
    fm, body = notes.read_front_matter(text)
    mark = fm.get(MARK) if isinstance(fm, dict) else None
    if mark:
        return "ours" if str(mark) == body_hash(body) else "edited"
    if legacy is not None and isinstance(fm, dict) and fm:
        try:
            if legacy(fm):
                return "ours"
        except Exception:  # noqa: BLE001
            pass
    return "theirs"


def is_ours(path: Path, legacy: Callable[[dict], bool] | None = None) -> bool:
    return ownership(path, legacy) == "ours"


def write_note(path: Path, fm: dict, body: str, legacy: Callable[[dict], bool] | None = None) -> bool:
    """Write a note with front matter, marked as Oso's. False (and nothing written) when the file is the
    student's or he edited it; True when it was written or was already the same."""
    state = ownership(path, legacy)
    if state in ("edited", "theirs"):
        log.info("not overwriting %s: %s", path.name, "the student edited it" if state == "edited" else "it is the student's")
        return False
    text = notes.with_front_matter({**{k: v for k, v in fm.items() if k != MARK}, MARK: body_hash(body)}, body)
    if state == "ours":
        try:
            if path.read_text(encoding="utf-8") == text:
                return True
        except OSError:
            pass
    write_file(path, text)
    return True


def write_file(path: Path, text: str) -> Path:
    """Write a file Oso owns outright (Today.md, Dashboard.md, Oso/...) in one piece."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".oso-tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def textbook_note(fm: dict) -> bool:
    return fm.get("type") == "textbook" and bool(fm.get("chapter"))


def book_index(fm: dict) -> bool:
    return fm.get("type") == "book"


def canvas_note(fm: dict) -> bool:
    return str(fm.get("type") or "").startswith("canvas-") or fm.get("type") == "announcement"


def web_page(fm: dict) -> bool:
    return fm.get("type") == "web-page"


def converted_copy(fm: dict) -> bool:
    return bool(fm.get("converted"))


def transcribed_note(fm: dict) -> bool:
    return fm.get("source") == "handwriting"
