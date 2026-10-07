"""Nightly backup to a folder the student chooses (a NAS share, an external drive, any folder).

Nothing happens unless a backup folder is set (`oso settings` or `oso backup --set-folder`). Then, on the
first check after `backup_hour` each day, Oso copies to that folder:

- `Vault/`: the whole vault, copying only files that changed. Files deleted from the vault are moved to
  `Removed/<date>/` instead of being deleted, and cleared after 30 days.
- `Oso/oso.sqlite`: a safe copy of Oso's database taken while it is in use, plus a dated copy each day
  in `Oso/history/`, kept 30 days.
- `Oso/config.toml`: the settings file (it holds no credentials; those stay in the credential store).

A night when the folder can't be reached is skipped quietly and tried again at the next check. A big first
backup that runs out of time continues at the next check. If backups stop for several days, Today.md says
so. `oso restore` brings a vault and database back from the folder.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config as cfgmod
from . import db
from .config import Config

META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"
KEEP_DAYS = 30
STALE_DAYS = 3
BUDGET_SECONDS = 8 * 60


class BackupError(Exception):
    """A plain-sentence reason a backup could not be made."""


def check_folder(folder: Path) -> None:
    """Make sure Oso can write to the folder: write a small file and remove it."""
    if not folder.is_dir():
        raise BackupError(f"Oso can't reach {folder}. Check that it exists and that you are connected to it.")
    probe = folder / f".oso-check-{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise BackupError(f"Oso can't write to {folder} ({e.strerror or type(e).__name__}).") from e


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    conn.executescript(META)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def last_success(conn: sqlite3.Connection) -> datetime | None:
    v = _meta(conn, "backup_last_ok")
    return datetime.fromisoformat(v) if v else None


def due(conn: sqlite3.Connection, cfg: Config, now: datetime) -> bool:
    if not cfg.backup_folder:
        return False
    last = last_success(conn)
    if last is not None and last.astimezone(now.tzinfo).date() >= now.date():
        return False
    return now.hour >= cfg.backup_hour or (last is not None and (now.date() - last.astimezone(now.tzinfo).date()).days > 1)


# ---- copying ----------------------------------------------------------------------------------------


def _same(src: Path, dst: Path) -> bool:
    try:
        a, b = src.stat(), dst.stat()
    except FileNotFoundError:
        return False
    return a.st_size == b.st_size and int(a.st_mtime) <= int(b.st_mtime)


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".oso-part")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _mirror(vault: Path, target: Path, removed_root: Path, today: date, deadline: float) -> dict[str, int]:
    counts = {"copied": 0, "bytes": 0, "removed": 0, "finished": 1}
    seen: set[str] = set()
    for src in vault.rglob("*"):
        if time.monotonic() > deadline:
            counts["finished"] = 0
            return counts
        if not src.is_file() or src.name.endswith(".oso-part"):
            continue
        rel = src.relative_to(vault)
        seen.add(rel.as_posix())
        dst = target / rel
        if not _same(src, dst):
            try:
                _copy(src, dst)
            except OSError:
                continue  # in use or gone; picked up next time
            counts["copied"] += 1
            counts["bytes"] += src.stat().st_size
    if target.is_dir():
        for dst in sorted(target.rglob("*"), reverse=True):
            rel = dst.relative_to(target).as_posix()
            if dst.is_file() and rel not in seen and not rel.endswith(".oso-part"):
                keep = removed_root / today.isoformat() / rel
                keep.parent.mkdir(parents=True, exist_ok=True)
                os.replace(dst, keep)
                counts["removed"] += 1
            elif dst.is_dir() and not any(dst.iterdir()):
                dst.rmdir()
    return counts


def _prune(folder: Path, today: date, pattern_date) -> None:
    if not folder.is_dir():
        return
    for p in folder.iterdir():
        d = pattern_date(p)
        if d is not None and (today - d).days > KEEP_DAYS:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)


def _date_of(p: Path) -> date | None:
    stem = p.name.removeprefix("oso-").removesuffix(".sqlite")
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None


def _database(dest_dir: Path, today: date) -> None:
    """A consistent copy of the live database, using SQLite's own backup, plus a dated copy."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / "oso.sqlite.oso-part"
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(str(db.db_path()))
    try:
        out = sqlite3.connect(str(tmp))
        with out:
            src.backup(out)
        out.close()
    finally:
        src.close()
    os.replace(tmp, dest_dir / "oso.sqlite")
    history = dest_dir / "history"
    history.mkdir(exist_ok=True)
    shutil.copy2(dest_dir / "oso.sqlite", history / f"oso-{today.isoformat()}.sqlite")
    _prune(history, today, _date_of)


def run(cfg: Config, conn: sqlite3.Connection, now: datetime, force: bool = False, budget: float = BUDGET_SECONDS) -> dict:
    """Back up if due (or now, with force). Returns a summary; never raises for an unreachable folder."""
    if not cfg.backup_folder:
        return {"skipped": "no backup folder set"}
    if not force and not due(conn, cfg, now):
        return {"skipped": "already backed up today"}
    folder = Path(cfg.backup_folder)
    _set(conn, "backup_last_try", now.isoformat(timespec="seconds"))
    try:
        check_folder(folder)
    except BackupError as e:
        return {"skipped": str(e)}
    today = now.date()
    deadline = time.monotonic() + budget
    counts = _mirror(cfg.vault, folder / "Vault", folder / "Removed", today, deadline)
    _prune(folder / "Removed", today, lambda p: _date_of(p))
    if not counts["finished"]:
        return {**counts, "note": "Big backup; it continues at the next check."}
    conn.commit()
    _database(folder / "Oso", today)
    cfg_file = cfgmod.config_path()
    if cfg_file.exists():
        _copy(cfg_file, folder / "Oso" / "config.toml")
    _set(conn, "backup_last_ok", now.isoformat(timespec="seconds"))
    _set(conn, "backup_last_summary", f"{counts['copied']} changed files")
    return counts


def stale_line(conn: sqlite3.Connection, cfg: Config, now: datetime) -> str | None:
    """The Today.md line when backups have stopped working, or None."""
    if not cfg.backup_folder:
        return None
    last = last_success(conn)
    if last is None:
        tried = _meta(conn, "backup_last_try")
        if tried and (now - datetime.fromisoformat(tried)).days >= 1:
            return f"Oso hasn't been able to make a backup yet: it can't reach {cfg.backup_folder}."
        return None
    days = (now - last.astimezone(now.tzinfo)).days
    if days >= STALE_DAYS:
        return f"Your notes haven't been backed up since {last.astimezone(now.tzinfo).strftime('%A %B %d')}: Oso can't reach {cfg.backup_folder}."
    return None


# ---- restoring ------------------------------------------------------------------------------------------


def restore(cfg: Config, folder: Path, day: str | None = None, overwrite: bool = False) -> list[str]:
    """Bring the vault, database, and settings back from a backup folder. Refuses to write over a vault
    that already has notes unless overwrite is set. Returns plain lines."""
    src_vault, src_oso = folder / "Vault", folder / "Oso"
    if not src_vault.is_dir() or not (src_oso / "oso.sqlite").exists():
        raise BackupError(f"{folder} doesn't hold an Oso backup.")
    has_notes = cfg.vault.is_dir() and any(p.suffix == ".md" for p in cfg.vault.rglob("*.md") if ".obsidian" not in p.parts)
    if has_notes and not overwrite:
        raise BackupError(f"{cfg.vault} already has notes in it. Restore into an empty vault, or confirm to write over it.")
    lines = []
    n = 0
    for src in src_vault.rglob("*"):
        if src.is_file():
            _copy(src, cfg.vault / src.relative_to(src_vault))
            n += 1
    lines.append(f"Restored {n} files into {cfg.vault}.")
    dbfile = src_oso / "oso.sqlite"
    if day:
        dbfile = src_oso / "history" / f"oso-{day}.sqlite"
        if not dbfile.exists():
            raise BackupError(f"There is no backup of Oso's records from {day}.")
    _copy(dbfile, db.db_path())
    lines.append("Restored Oso's records" + (f" from {day}." if day else "."))
    if (src_oso / "config.toml").exists():
        old = cfgmod.load(src_oso / "config.toml")
        old.vault = cfg.vault  # keep this computer's vault location
        cfgmod.save(old)
        lines.append("Restored your settings and courses.")
    lines.append("Reconnect what lives in this computer's credential store: run 'oso init' for the Canvas feed, "
                 "'oso connect-canvas', and Connect Google Calendar in 'oso settings'.")
    return lines
