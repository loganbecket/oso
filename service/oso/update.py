"""Keep the installed service current with the repository it was installed from.

`oso set-repo <path>` (the installers run it) records where the clone lives and which commit is installed.
`oso update` pulls the clone, reinstalls the service from it, and re-registers the scheduler.
Once a day the sync checks whether the repository is ahead of what is installed and says so in Today.md
and in `oso doctor`.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import config as cfgmod
from .config import Config
from .db import now_iso

META = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _git(repo: Path, *args: str, timeout: int = 60) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout, check=True)
    return r.stdout.strip()


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def set_repo(cfg: Config, path: Path) -> str:
    if not (path / ".git").exists():
        raise ValueError(f"{path} is not a git clone of Oso")
    cfg.repo_path = str(path.resolve())
    cfg.installed_commit = head(path)
    cfgmod.save(cfg)
    return cfg.installed_commit


def status(cfg: Config, fetch: bool = True) -> dict:
    """What is installed, what the clone has, what the remote has."""
    if not cfg.repo_path:
        return {"known": False, "available": False, "message": "Oso does not know where its repository is. Run 'oso set-repo <path to the cloned folder>'."}
    repo = Path(cfg.repo_path)
    if not (repo / ".git").exists():
        return {"known": False, "available": False, "message": f"The Oso folder {repo} is gone. Clone it again and run 'oso set-repo'."}
    if not shutil.which("git"):
        return {"known": True, "available": False, "message": "git is not installed, so Oso cannot check for updates."}
    try:
        if fetch:
            _git(repo, "fetch", "--quiet", "origin", timeout=90)
        remote = _git(repo, "rev-parse", "origin/master")
        behind = int(_git(repo, "rev-list", "--count", f"{cfg.installed_commit or 'HEAD'}..origin/master") or 0) if cfg.installed_commit else 0
    except (subprocess.SubprocessError, OSError) as e:
        return {"known": True, "available": False, "message": f"Could not check for updates: {_plain(e)}"}
    available = bool(cfg.installed_commit) and remote != cfg.installed_commit
    msg = f"An Oso update is available ({behind} new change{'s' if behind != 1 else ''}). Run 'oso update'." if available else "Oso is up to date."
    return {"known": True, "available": available, "behind": behind, "installed": cfg.installed_commit, "remote": remote, "message": msg}


def check_daily(conn: sqlite3.Connection, cfg: Config, now: datetime) -> str | None:
    """Fetch at most once a day; return the update message to show, or None when nothing to say."""
    conn.executescript(META)
    row = conn.execute("SELECT value FROM meta WHERE key = 'update_checked_at'").fetchone()
    last = datetime.fromisoformat(row["value"]) if row else None
    if last is not None and now.astimezone(last.tzinfo) - last < timedelta(hours=24):
        cached = conn.execute("SELECT value FROM meta WHERE key = 'update_message'").fetchone()
        return cached["value"] if cached and cached["value"] else None
    st = status(cfg, fetch=True)
    message = st["message"] if (st.get("available") or not st.get("known")) else ""
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_checked_at', ?)", (now_iso(),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_message', ?)", (message,))
    return message or None


def run(cfg: Config) -> str:
    """Pull, reinstall, re-register the scheduler. Returns a report."""
    if not cfg.repo_path:
        return "Oso does not know where its repository is. Run 'oso set-repo <path to the cloned folder>' first."
    repo = Path(cfg.repo_path)
    lines = []
    try:
        before = head(repo)
        _git(repo, "pull", "--ff-only", "--quiet", "origin", "master", timeout=120)
        after = head(repo)
    except (subprocess.SubprocessError, OSError) as e:
        return f"Could not pull the latest Oso: {_plain(e)}"
    lines.append("Already current." if before == after else f"Pulled {_git(repo, 'rev-list', '--count', f'{before}..{after}')} new change(s).")
    uv = shutil.which("uv")
    if not uv:
        return "\n".join(lines + ["uv is not installed; run the installer script again to finish updating."])
    try:
        subprocess.run([uv, "tool", "install", "--force", "--python", "3.12", str(repo)], capture_output=True, text=True, timeout=600, check=True)
    except subprocess.SubprocessError as e:
        return "\n".join(lines + [f"Reinstall failed: {_plain(e)}"])
    cfg.installed_commit = after
    cfgmod.save(cfg)
    lines.append("Service reinstalled.")
    lines.append(_reschedule(cfg))
    return "\n".join(lines)


def _reschedule(cfg: Config) -> str:
    if sys.platform == "win32":
        from .install_windows import install_task

        return install_task(every_minutes=cfg.sync_interval_minutes)
    if sys.platform == "darwin":
        from .install_macos import install_agent

        return install_agent(every_minutes=cfg.sync_interval_minutes)
    from .install_linux import install_timer

    return install_timer(every_minutes=cfg.sync_interval_minutes)


def _plain(e: Exception) -> str:
    text = getattr(e, "stderr", None) or str(e)
    return (text or type(e).__name__).strip().splitlines()[-1][:160]
