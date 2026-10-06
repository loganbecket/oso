"""`oso fresh-start`: back to a fresh installation without redoing setup.

Kept: the settings (vault location, time zone, check schedule, urgency and quiet hours, models, update
channel), the Canvas feed and token and the Google Calendar connection in the credential store, the
scheduled check, Obsidian's own settings and plugins (`.obsidian`), and the downloaded search model.

Deleted, with no backup: everything else in the vault, the courses and anything tied to them (muted
courses, Drive folder links), and Oso's database (deadlines, grades, alerts, transcription history), its
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
    """What would be deleted from the vault."""
    return sorted(p for p in cfg.vault.iterdir() if p.name not in KEEP_IN_VAULT)


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
    lines.append(f"Deleted {removed} item{'s' if removed != 1 else ''} from the vault (kept Obsidian's settings).")

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
