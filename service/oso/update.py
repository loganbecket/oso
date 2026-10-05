"""Install and update the service from GitHub's downloads, with no Git.

Two channels:
- stable: the newest version tag (v1.2.3) on the repository. Until one exists, stable falls back to latest.
- latest: whatever is on the master branch.

Stable is the default; switching to latest is done in the settings window (`channel` in the config).
`oso update` installs the newest version on the configured channel; `oso update --version v0.1.0` (or a
commit) installs that exact version, for rolling back.
Once a day the sync asks GitHub whether something newer exists and says so in Today.md and `oso doctor`.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

import requests

from . import config as cfgmod
from .config import Config
from .db import now_iso

API = "https://api.github.com/repos/{repo}"
ZIP_BRANCH = "https://github.com/{repo}/archive/refs/heads/master.zip"
ZIP_TAG = "https://github.com/{repo}/archive/refs/tags/{tag}.zip"
ZIP_COMMIT = "https://github.com/{repo}/archive/{sha}.zip"
CHANNELS = ("stable", "latest")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"


class UpdateError(Exception):
    pass


def _get(url: str, **kw):
    r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=20, **kw)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise UpdateError("GitHub is limiting requests right now; try again in an hour")
    r.raise_for_status()
    return r


def newest_tag(repo: str) -> str | None:
    """The highest version tag (v1.2.3), or None if the repository has none."""
    tags = [t["name"] for t in _get(API.format(repo=repo) + "/tags", params={"per_page": 100}).json()]
    versions = [(tuple(int(x) for x in m.groups()), t) for t in tags if (m := _SEMVER.match(t))]
    return max(versions)[1] if versions else None


def master_commit(repo: str) -> str:
    return _get(API.format(repo=repo) + "/commits/master").json()["sha"]


def target(cfg: Config) -> dict:
    """What the chosen channel points to right now: version label, download URL, and the note to show."""
    if cfg.channel == "stable":
        tag = newest_tag(cfg.repo)
        if tag:
            return {"version": tag, "url": ZIP_TAG.format(repo=cfg.repo, tag=tag), "fallback": False}
    sha = master_commit(cfg.repo)
    return {"version": sha[:12], "url": ZIP_BRANCH.format(repo=cfg.repo), "fallback": cfg.channel == "stable"}


def status(cfg: Config) -> dict:
    try:
        t = target(cfg)
    except (requests.RequestException, UpdateError, KeyError, ValueError) as e:
        return {"known": False, "available": False, "message": f"Could not check for Oso updates: {_plain(e)}"}
    installed = cfg.installed_version
    available = installed is not None and installed != t["version"]
    where = "the latest version" if cfg.channel == "latest" or t["fallback"] else f"version {t['version']}"
    msg = f"An Oso update is available ({where}). Run 'oso update'." if available else f"Oso is up to date ({cfg.channel})."
    if t["fallback"]:
        msg += " No stable release has been tagged yet, so stable follows the latest version for now."
    return {"known": True, "available": available, "installed": installed, "target": t["version"], "message": msg}


def check_daily(conn: sqlite3.Connection, cfg: Config, now: datetime) -> str | None:
    """Ask GitHub at most once a day; return the message to show in Today.md, or None."""
    conn.executescript(META)
    row = conn.execute("SELECT value FROM meta WHERE key = 'update_checked_at'").fetchone()
    last = datetime.fromisoformat(row["value"]) if row else None
    if last is not None and now.astimezone(last.tzinfo) - last < timedelta(hours=24):
        cached = conn.execute("SELECT value FROM meta WHERE key = 'update_message'").fetchone()
        return cached["value"] if cached and cached["value"] else None
    st = status(cfg)
    message = st["message"] if st["available"] else ""
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_checked_at', ?)", (now_iso(),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_message', ?)", (message,))
    return message or None


def run(cfg: Config, channel: str | None = None, version: str | None = None) -> str:
    """Install the newest version on the channel, or an exact version or commit. Returns a report."""
    if channel:
        if channel not in CHANNELS:
            return f"Channel must be one of: {', '.join(CHANNELS)}."
        cfg.channel = channel
    try:
        if version:
            if _SEMVER.match(version):
                t = {"version": version, "url": ZIP_TAG.format(repo=cfg.repo, tag=version), "fallback": False}
            else:
                t = {"version": version[:12], "url": ZIP_COMMIT.format(repo=cfg.repo, sha=version), "fallback": False}
        else:
            t = target(cfg)
    except (requests.RequestException, UpdateError, KeyError, ValueError) as e:
        return f"Could not reach GitHub: {_plain(e)}"
    lines = []
    if not version and cfg.installed_version == t["version"]:
        cfgmod.save(cfg)
        return f"Oso is already at {t['version']} on the {cfg.channel} channel."
    try:
        install(t["url"])
    except UpdateError as e:
        return f"Could not install Oso {t['version']}: {e}"
    cfg.installed_version = t["version"]
    cfgmod.save(cfg)
    lines.append(f"Installed Oso {t['version']} ({'pinned' if version else cfg.channel}).")
    if t["fallback"]:
        lines.append("No stable release has been tagged yet, so this is the latest version.")
    lines.append(_reschedule(cfg))
    return "\n".join(lines)


def install(url: str) -> None:
    uv = shutil.which("uv")
    if not uv:
        raise UpdateError("uv is not installed; run the Oso installer again")
    r = subprocess.run([uv, "tool", "install", "--force", "--python", "3.12", url], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise UpdateError((r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout) else "uv failed")


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
    text = str(e) or type(e).__name__
    return text.strip().splitlines()[-1][:160]
