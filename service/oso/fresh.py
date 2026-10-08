"""`oso fresh-start`: back to a fresh installation without redoing setup.

Kept: the settings (vault location, time zone, check schedule, urgency and quiet hours, models, update
channel, backup folder; the backup itself is outside the vault and is not touched), the Canvas feed and token and the Google Calendar, school email, and GroupMe connections in the credential store, the
scheduled check, the Canvas sign-in, Obsidian's own settings and plugins (`.obsidian`), the courses' textbooks
(each course's `Books` folder, with what Oso has read of them), his feedback about Oso (`Oso/Feedback`), and the downloaded
search model. Everything read from Canvas is cleared and read again on the next check.

Deleted, with no backup: everything else in the vault (his rules in `Oso/Rules` among it), the courses and anything tied to them (muted
courses, Drive folder links), and Oso's database (deadlines, grades, alerts, transcription history, and the
learner profile: every quiz, check, and topic rating, what was picked out of email and GroupMe, and what Claude noted in conversations: confusion, misconceptions,
preferences, and goals), its
search index, and its record of the command instructions. A sync then rebuilds the starting folders,
`Today.md`, and the command instructions, and pulls the Canvas deadlines back in.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import config as cfgmod
from . import db, search
from .config import Config

KEEP_IN_VAULT = {".obsidian"}
BOOKS = "Books"  # a course's textbooks are purchases, not Oso's records: kept, with what Oso has read of them


class NotAVault(Exception):
    pass


def check_vault(vault: Path) -> None:
    """Refuse anything that does not look like an Oso vault, so a bad setting can never empty a home folder or a drive."""
    v = vault.resolve()
    if not v.is_dir():
        raise NotAVault(f"{vault} is not a folder.")
    if v == Path(v.anchor) or v == Path.home().resolve() or len(v.parts) < 3:
        raise NotAVault(f"{vault} is a top-level folder, not a vault.")
    if not any((v / marker).exists() for marker in (".obsidian", "Today.md", "Courses", "Oso")):
        raise NotAVault(f"{vault} does not look like an Oso vault (no .obsidian, Today.md, Courses, or Oso inside).")


def plan(cfg: Config) -> list[Path]:
    """What would be deleted from the vault: everything except Obsidian's settings, the courses' Books folders,
    and his feedback about Oso in Oso/Feedback, which is meant for whoever builds Oso (the folders around a kept
    folder are kept only as far as needed to hold it)."""
    keep = {p.resolve() for p in (cfg.vault / "Courses").rglob(BOOKS) if p.is_dir()} if (cfg.vault / "Courses").is_dir() else set()
    if (cfg.vault / "Oso" / "Feedback").is_dir():
        keep.add((cfg.vault / "Oso" / "Feedback").resolve())
    out: list[Path] = []

    def walk(folder: Path) -> None:
        for p in folder.iterdir():
            r = p.resolve()
            if r in keep:
                continue
            if p.is_dir() and any(k.is_relative_to(r) for k in keep):
                walk(p)  # holds a Books folder somewhere inside: look deeper
            else:
                out.append(p)

    for p in cfg.vault.iterdir():
        if p.name in KEEP_IN_VAULT:
            continue
        if p.is_dir() and any(k.is_relative_to(p.resolve()) for k in keep):
            walk(p)
        else:
            out.append(p)
    return sorted(out)


def run(cfg: Config) -> list[str]:
    """Delete, reset, and rebuild. Returns plain lines describing what happened."""
    check_vault(cfg.vault)
    lines = []
    problems = []
    removed = 0
    for p in plan(cfg):
        try:
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
            removed += 1
        except OSError as e:
            problems.append(f"Could not delete {p.name} ({e.strerror or type(e).__name__}); close any program using it and run this again.")
    lines.append(f"Deleted {removed} item{'s' if removed != 1 else ''} from the vault (kept Obsidian's settings and your textbooks).")

    cfg.courses = []
    cfg.muted_courses = []
    cfgmod.save(cfg)
    lines.append("Cleared the courses; every other setting is kept.")

    for path in (db.db_path(), search.index_path()):
        for f in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm"), path.with_name(path.name + "-journal")):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                problems.append(f"Could not reset {f.name}; close the Claude app and run this again.")
    shutil.rmtree(cfgmod.data_dir() / "skills", ignore_errors=True)
    lines.append("Reset deadlines, grades, alerts, transcription history, and search.")

    for sub in ("Clippings", "Courses", "Oso"):
        (cfg.vault / sub).mkdir(parents=True, exist_ok=True)
    return lines + problems
