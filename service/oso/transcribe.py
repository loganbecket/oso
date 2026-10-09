"""`oso transcribe`: turn queued page images into notes, one page per Claude Code call.

Each page is sent to Claude Code non-interactively (`claude -p`) with the model from settings, so no
page image lingers in a growing conversation. The pages of a notebook are appended to one note in the
course's Notes folder. Confidence comes back on the last line of each reply.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from . import handwriting, notes, vault
from .config import Config

log = logging.getLogger("oso.transcribe")

PROMPT = """Read the image file at "{image}" (use your Read tool). It is page {page} of a student's handwritten notebook called "{notebook}" for the course {course}.

Transcribe it faithfully as Markdown:
- Keep the student's wording and order. Fix nothing except obvious slips.
- Headings where the student drew them; lists as lists.
- Every equation in LaTeX: $...$ inline, $$...$$ on its own line.
- Each diagram, graph, or sketch as a blockquote starting "> Figure:" describing what it shows in one or two sentences, including axis labels and any values written on it.
- Anything unreadable as [?]. Never guess.
- Do not summarize, comment, or add anything that is not on the page.

Output only the transcription, then a final line exactly like:
CONFIDENCE: 0.85
where the number (0 to 1) is how completely and accurately you could read the page."""

_CONF = re.compile(r"^CONFIDENCE:\s*([01](?:\.\d+)?)\s*$", re.MULTILINE)


class ClaudeMissing(Exception):
    pass


def run(conn: sqlite3.Connection, cfg: Config, limit: int = 200, model: str | None = None) -> dict[str, int]:
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeMissing("Claude Code is not installed or not on PATH. Install it from claude.ai/code and sign in.")
    model = model or cfg.transcribe_model
    handwriting.queue_new(conn, cfg)  # scans saved since the last sync
    pages = handwriting.pending(conn, limit=limit)
    counts = {"pages": 0, "notes": 0, "low_confidence": 0, "failed": 0}
    by_notebook: dict[tuple[str | None, str, str], list[dict]] = {}
    for p in pages:
        by_notebook.setdefault((p["course"], p["notebook"], p["source_file"]), []).append(p)

    for (course, notebook, _source), items in by_notebook.items():
        note_path = _note_path(cfg, course, notebook, items[0]["queued_at"])
        if vault.ownership(note_path, vault.transcribed_note) in ("edited", "theirs"):
            note_path = note_path.with_name(f"{note_path.stem} (continued).md")  # his edits stay his; new pages go beside them
        if not note_path.exists():
            fm, body = _header(cfg, course, notebook)
            vault.write_note(note_path, fm, body)
        lowest: float | None = None
        for p in items:
            try:
                text, conf = _transcribe_page(exe, cfg, model, p, course)
            except subprocess.SubprocessError as e:
                log.warning("page %s of %s failed: %s", p["page"], notebook, type(e).__name__)
                counts["failed"] += 1
                continue
            fm, body = notes.read_front_matter(note_path.read_text(encoding="utf-8"))
            vault.write_note(note_path, fm, body.rstrip("\n") + f"\n\n## Page {p['page']}\n\n{text.strip()}\n\n![[{p['path']}]]\n")
            handwriting.mark(conn, p["path"], str(note_path.relative_to(cfg.vault)), conf)
            conn.commit()
            counts["pages"] += 1
            if conf < 0.7:
                counts["low_confidence"] += 1
            lowest = conf if lowest is None else min(lowest, conf)
        if lowest is not None:
            _set_confidence(note_path, lowest)
        counts["notes"] += 1
    return counts


def _transcribe_page(exe: str, cfg: Config, model: str, p: dict, course: str | None) -> tuple[str, float]:
    image = cfg.vault / p["path"]
    c = cfg.course_for(course)
    prompt = PROMPT.format(image=image, page=p["page"], notebook=p["notebook"], course=c.name if c else (course or "an unknown course"))
    result = subprocess.run(
        [exe, "-p", "--model", model, "--output-format", "text", "--allowedTools", "Read", "--strict-mcp-config", "--max-turns", "4"],
        input=prompt,
        cwd=str(cfg.vault),
        encoding="utf-8",
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.SubprocessError((result.stderr or result.stdout).strip()[:200])
    out = result.stdout
    m = _CONF.search(out)
    conf = float(m.group(1)) if m else 0.5
    text = _CONF.sub("", out).strip()
    return text, conf


def _note_path(cfg: Config, course: str | None, notebook: str, queued_at: str) -> Path:
    day = datetime.fromisoformat(queued_at).astimezone(cfg.tz).strftime("%Y-%m-%d")
    name = f"{day} {notes.safe_name(notebook)}.md"
    c = cfg.course_for(course)
    if c is None:
        raise ValueError(f"no course {course!r} for handwritten page")
    return cfg.vault / "Courses" / c.folder / "Notes" / name


def _header(cfg: Config, course: str | None, notebook: str) -> tuple[dict, str]:
    c = cfg.course_for(course)
    fm = {"type": "notes", "course": c.code if c else None, "source": "handwriting", "notebook": notebook, "transcribed": notes.stamp(), "confidence": None}
    return fm, f"# {notebook}\n"


def _set_confidence(note_path: Path, value: float) -> None:
    fm, body = notes.read_front_matter(note_path.read_text(encoding="utf-8"))
    fm["confidence"] = round(value, 2)
    vault.write_note(note_path, fm, body)
