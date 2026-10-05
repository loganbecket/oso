"""`oso doctor`: check the installation and fix what can be fixed, in plain language."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import config as cfgmod
from . import db, secrets


def run(fix: bool = False) -> list[tuple[str, str]]:
    """Returns (status, message) pairs; status is ok, warn, or fail."""
    out: list[tuple[str, str]] = []
    try:
        cfg = cfgmod.load()
    except cfgmod.ConfigError as e:
        return [("fail", str(e))]
    out.append(("ok", f"Settings found at {cfgmod.config_path()}"))

    if cfg.vault.is_dir():
        out.append(("ok", f"Vault at {cfg.vault}"))
        for sub in ("Inbox", "Inbox/Handwriting", "Courses"):
            p = cfg.vault / sub
            if not p.is_dir():
                if fix:
                    p.mkdir(parents=True, exist_ok=True)
                    out.append(("ok", f"Created missing folder {sub}"))
                else:
                    out.append(("warn", f"Vault folder {sub} is missing (run with --fix to create it)"))
    else:
        out.append(("fail", f"The vault folder {cfg.vault} does not exist. Run 'oso init --vault <path>' with the right path."))

    if not cfg.courses:
        out.append(("warn", "No courses set up yet. Run the course setup skill in Cowork or Claude Code with a syllabus in the vault."))
    else:
        out.append(("ok", f"{len(cfg.courses)} course{'s' if len(cfg.courses) != 1 else ''} set up"))
        for c in cfg.courses:
            if not (cfg.vault / "Courses" / c.folder).is_dir():
                out.append(("warn", f"Folder for {c.name} is missing: Courses/{c.folder}"))

    feed = secrets.get(secrets.CANVAS_FEED_URL)
    token = secrets.get(secrets.CANVAS_TOKEN)
    if not feed and not token:
        out.append(("fail", "No Canvas source. Run 'oso init' again and paste the Calendar Feed URL from Canvas."))
    else:
        out.append(("ok", "Canvas feed URL stored" if feed else "Canvas token stored"))

    with db.connect() as conn:
        rows = db.connector_health(conn)
        now = datetime.now().astimezone()
        if not rows:
            out.append(("warn", "No sync has run yet. Run 'oso sync'."))
        for r in rows:
            if not r["last_success"]:
                out.append(("fail", f"{r['connector']} has never succeeded: {r['last_error']}"))
                continue
            age = now - datetime.fromisoformat(r["last_success"])
            if age > timedelta(hours=24):
                out.append(("warn", f"{r['connector']} last succeeded {int(age.total_seconds() // 3600)} hours ago. Is the scheduled task running? Try 'oso install-task'."))
            else:
                out.append(("ok", f"{r['connector']} synced within the last day"))
        if not (cfg.vault / "Today.md").exists():
            out.append(("warn", "Today.md has not been written yet. Run 'oso sync'."))

    if sys.platform == "win32":
        if shutil.which("schtasks"):
            import subprocess

            r = subprocess.run(["schtasks", "/Query", "/TN", "Oso Sync"], capture_output=True, text=True)
            if r.returncode == 0:
                out.append(("ok", "Scheduled task 'Oso Sync' is installed"))
            else:
                out.append(("warn", "Scheduled task is not installed. Run 'oso install-task'."))
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "oso-sync.timer"
        out.append(("ok", "systemd timer installed") if unit.exists() else ("warn", "Timer not installed. Run 'oso install-task'."))

    if not shutil.which("oso-mcp"):
        out.append(("warn", "The 'oso-mcp' command is not on PATH, so Cowork and Claude Code cannot reach Oso's tools. Reinstall with 'uv tool install'."))
    return out


def format_report(results: list[tuple[str, str]]) -> str:
    icon = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}
    return "\n".join(f"{icon[s]}  {m}" for s, m in results)
