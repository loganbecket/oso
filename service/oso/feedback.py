"""Feedback about Oso from the student: bugs and ideas, one note each in `Oso/Feedback/`.

The notes ride along in the nightly backup, so whoever builds Oso can pick them up from there. Each has his
words as he said them, a one-line summary, the kind (bug or idea), what he was doing, the Oso version, and
the date.

When a release takes care of a note, its code (`code`, a short hash that says nothing about the note to anyone
reading this repo) goes in `shipped_feedback.txt`. After he updates, the next check deletes the note and the
briefing tells him once that it is in Oso now.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import notes
from .config import Config

FOLDER = ("Oso", "Feedback")
KINDS = ("bug", "idea")
SHIPPED = Path(__file__).with_name("shipped_feedback.txt")
SHOWN_FOR = timedelta(hours=36)  # long enough to reach the next morning briefing


def save(cfg: Config, words: str, kind: str, summary: str, doing: str | None = None, now: datetime | None = None) -> Path:
    from . import version_label

    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be bug or idea, not {kind!r}")
    if not (words or "").strip() or not (summary or "").strip():
        raise ValueError("feedback needs his words and a one-line summary")
    now = now or datetime.now(cfg.tz)
    folder = cfg.vault.joinpath(*FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9 ]+", "", summary).strip()[:60].strip() or kind
    path = folder / f"{now.strftime('%Y-%m-%d %H%M')} {kind} - {notes.safe_name(slug)}.md"
    n = 2
    while path.exists():
        path = path.with_name(f"{path.stem} ({n}).md")
        n += 1
    fm = {"type": "oso-feedback", "kind": kind, "status": "new", "date": now.isoformat(timespec="minutes"),
          "oso": version_label(cfg.installed_version), "summary": summary.strip()}
    quoted = "\n".join(f"> {line}" if line else ">" for line in words.strip().splitlines())
    body = f"# {summary.strip()}\n\n## In his words\n\n{quoted}\n"
    if doing and doing.strip():
        body += f"\n## What he was doing\n\n{doing.strip()}\n"
    path.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
    return path


def code(fm: dict) -> str:
    """The note's code: the same for the same note on any computer, and nothing readable about it."""
    return hashlib.sha256(f"{fm.get('date')}|{str(fm.get('summary') or '').strip()}".encode()).hexdigest()[:12]


def shipped() -> dict[str, str]:
    """Codes of notes a release took care of, with the version that did."""
    out = {}
    if SHIPPED.exists():
        for line in SHIPPED.read_text(encoding="utf-8").splitlines():
            parts = line.split("#")[0].split()
            if len(parts) == 2:
                out[parts[0]] = parts[1]
    return out


def close_shipped(cfg: Config, conn: sqlite3.Connection, now: datetime) -> int:
    """Delete his notes that a release took care of and remember them for the briefing. Returns how many."""
    done = shipped()
    folder = cfg.vault.joinpath(*FOLDER)
    if not done or not folder.is_dir():
        return 0
    closed = []
    for path in sorted(folder.glob("*.md")):
        fm, _ = notes.read_front_matter(path.read_text(encoding="utf-8"))
        version = done.get(code(fm)) if fm.get("type") == "oso-feedback" else None
        if version:
            closed.append(f"{'Your' if fm.get('kind') == 'idea' else 'The'} {fm.get('kind') or 'feedback'} \"{fm.get('summary')}\" "
                          f"{'is in' if fm.get('kind') == 'idea' else 'was fixed in'} Oso {version}.")
            path.unlink()
    for line in closed:
        conn.execute("INSERT INTO feedback_shipped (line, shipped_at) VALUES (?, ?)", (line, now.isoformat(timespec="minutes")))
    return len(closed)


def recent_lines(conn: sqlite3.Connection, now: datetime) -> list[str]:
    since = (now - SHOWN_FOR).isoformat(timespec="minutes")
    return [r[0] for r in conn.execute("SELECT line FROM feedback_shipped WHERE shipped_at >= ? ORDER BY id", (since,))]
