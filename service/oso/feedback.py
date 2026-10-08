"""Feedback about Oso from the student: bugs and ideas, one note each in `Oso/Feedback/`.

The notes ride along in the nightly backup, so whoever builds Oso can pick them up from there. Each has his
words as he said them, a one-line summary, the kind (bug or idea), what he was doing, the Oso version, and
the date.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import notes
from .config import Config

FOLDER = ("Oso", "Feedback")
KINDS = ("bug", "idea")


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
