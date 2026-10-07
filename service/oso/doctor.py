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
    return [(c["status"], c["text"]) for c in checks(fix)]


# What fixes each kind of problem; the status panel puts a button beside the line, and Claude can offer it.
ACTIONS = {
    "update": "Update Oso",
    "fix": "Fix",
    "sync": "Sync now",
    "connect_canvas": "Sign in to Canvas",
    "connect_calendar": "Connect Google Calendar",
    "connect_email": "Connect email",
    "backup": "Back up now",
}


class _Out(list):
    """The list of checks; `add` takes an optional action that fixes the problem."""

    def append(self, item, action: str | None = None):  # noqa: D401 - list-compatible
        status, text = item
        super().append({"status": status, "text": text, "action": action if status != "ok" else None})


def checks(fix: bool = False) -> list[dict]:
    """Every check as {status, text, action}: status ok, warn, or fail; action the fix's name, if any."""
    out = _Out()
    try:
        cfg = cfgmod.load()
    except cfgmod.ConfigError as e:
        return [{"status": "fail", "text": str(e), "action": None}]
    from . import __version__

    version = cfg.installed_version or __version__
    out.append(("ok", f"Oso {version if version.startswith('v') or len(version) > 8 else 'v' + version}, following {cfg.channel} updates"))
    out.append(("ok", f"Settings found at {cfgmod.config_path()}"))

    if cfg.vault.is_dir():
        out.append(("ok", f"Vault at {cfg.vault}"))
        for sub in ("Clippings", "Courses", "Oso"):
            p = cfg.vault / sub
            if not p.is_dir():
                if fix:
                    p.mkdir(parents=True, exist_ok=True)
                    out.append(("ok", f"Created missing folder {sub}"))
                else:
                    out.append(("warn", f"Vault folder {sub} is missing (run with --fix to create it)"), "fix")
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
            out.append(("warn", "No sync has run yet. Run 'oso sync'."), "sync")
        for r in rows:
            if not r["last_success"]:
                out.append(("fail", f"{_name(r['connector'])} has never worked: {r['last_error']}"),
                           "connect_canvas" if r["connector"] == "canvas_api" else None)
                continue
            age = now - datetime.fromisoformat(r["last_success"])
            if age > timedelta(hours=24):
                if r["connector"] == "remarkable_usb":
                    out.append(("ok", f"reMarkable last pulled {_ago(age)} (it pulls when plugged in)"))
                else:
                    out.append(("warn", f"{_name(r['connector'])} last worked {_ago(age)}. Is the automatic check running?"), "sync")
            else:
                out.append(("ok", f"{_name(r['connector'])} last worked {_ago(age)}"))
        if not (cfg.vault / "Today.md").exists():
            out.append(("warn", "Today.md has not been written yet. Run 'oso sync'."), "sync")

    if sys.platform == "win32":
        if shutil.which("schtasks"):
            import subprocess

            r = subprocess.run(["schtasks", "/Query", "/TN", "Oso Sync"], capture_output=True, text=True)
            if r.returncode == 0:
                out.append(("ok", "Scheduled task 'Oso Sync' is installed"))
            else:
                out.append(_schedule_missing(cfg, fix, "Scheduled task"), "fix")
    elif sys.platform == "darwin":
        from .install_macos import installed

        out.append(("ok", "Launch agent installed") if installed() else _schedule_missing(cfg, fix, "Launch agent"), "fix")
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "oso-sync.timer"
        out.append(("ok", "systemd timer installed") if unit.exists() else _schedule_missing(cfg, fix, "Timer"), "fix")

    if cfg.backup_folder:
        from . import backup

        with db.connect() as conn:
            last = backup.last_success(conn)
            stale = backup.stale_line(conn, cfg, datetime.now(cfg.tz))
        if stale:
            out.append(("warn", stale), "backup")
        elif last:
            out.append(("ok", f"Last backup to {cfg.backup_folder}: {last.astimezone(cfg.tz).strftime('%a %b %d %H:%M')}"))
        else:
            out.append(("ok", f"Backups go to {cfg.backup_folder}; the first runs tonight (or run 'oso backup')"))

    from . import watch

    if watch.alive():
        out.append(("ok", "Folder watcher is running: new files are taken in as soon as they arrive"))
    elif fix:
        from .update import _reschedule

        _reschedule(cfg)
        out.append(("ok", "Folder watcher was not running; restarted it"))
    else:
        out.append(("warn", "The folder watcher isn't running, so new files wait for the next check. Run 'oso doctor --fix'."), "fix")

    from . import gcal

    if gcal.connected():
        out.append(("ok", "Google Calendar connected for alerts"))
    else:
        out.append(("warn", "Google Calendar is not connected, so urgent changes only appear in Today.md and Oso/Alerts.md. See 'Connect the Oso calendar' in the README."), "connect_calendar")

    from . import groupme, mail, messages

    if mail.connected():
        out.append(("ok", f"Reading email at {mail.address() or 'the connected account'}"))
    else:
        out.append(("warn", "Email isn't connected, so Oso can't see moved deadlines or events announced by email. Run 'oso connect-email'."), "connect_email")
    if groupme.connected():
        with db.connect() as conn:
            gs = groupme.groups(conn)
        muted = sum(1 for g in gs if g["id"] in set(cfg.muted_groups))
        out.append(("ok", f"Reading GroupMe ({len(gs) - muted} group{'s' if len(gs) - muted != 1 else ''}" + (f", {muted} muted)" if muted else ")")))
    else:
        out.append(("ok", "GroupMe isn't connected (optional; connect it on the Actions tab if you use GroupMe)"))
    with db.connect() as conn:
        unread = messages.waiting(conn)
    if unread:
        from . import reader

        if reader._claude() is None:
            out.append(("warn", f"{unread} messages are waiting for Claude, but Claude Code isn't installed. Install it from claude.ai/code."))
        else:
            out.append(("ok", f"Claude is reading {unread} new messages in the background"))

    from . import update

    st = update.status(cfg)
    if not st["known"] or st["available"]:
        out.append(("warn", st["message"]), "update" if st["available"] else None)
    else:
        out.append(("ok", st["message"]))

    from . import canvas_session

    with db.connect() as conn:
        cs = canvas_session.status(conn)
        hours = canvas_session.lifetimes(conn)
    if cs == "connected":
        out.append(("ok", "Canvas connected through your sign-in" + (f" (sessions have lasted about {sorted(hours)[len(hours) // 2]:g} hours)" if hours else "")))
    elif cs == "needs_sign_in":
        out.append(("warn", canvas_session.SIGN_IN_LINE), "connect_canvas")
    elif not secrets.get(secrets.CANVAS_TOKEN):
        out.append(("warn", "Canvas grades and coursework are not connected; only due dates come in. Run 'oso connect-canvas' to sign in."), "connect_canvas")

    from . import tutor

    with db.connect() as conn:
        for c in cfg.courses:
            gen = tutor.generosity(conn, c.code)
            if gen and gen.get("line"):
                out.append(("warn", f"{c.name}: {gen['line']} The quiz instructions now say to grade strictly."))

    from . import books

    for b in books.progress(cfg):
        if b["error"]:
            out.append(("warn", f"{b['book']}: {b['error']} Run 'oso books --reprocess \"{b['book']}\"' after replacing the file."))
        elif not b["total"] or b["done"] < b["total"]:
            out.append(("ok", f"Reading {b['book']}: {b['done']} of {b['total'] or '?'} pages so far; it continues on each check"))
        else:
            out.append(("ok", f"{b['book']} is read" + (f" ({b['poor']} pages are mostly equations or figures; Claude reads those when asked)" if b["poor"] else "")))

    from . import reader

    with db.connect() as conn:
        waiting_pages = len(reader.waiting(cfg, conn, datetime.now(cfg.tz))) + reader.handwriting_waiting(conn)
    if waiting_pages:
        if not cfg.auto_read:
            out.append(("warn", f"{waiting_pages} pages with handwriting, equations, tables, or drawings are waiting; automatic reading is off in oso settings."))
        elif reader._claude() is None:
            out.append(("warn", f"{waiting_pages} pages are waiting for Claude, but Claude Code isn't installed. Install it from claude.ai/code."))
        else:
            out.append(("ok", f"Claude is reading {waiting_pages} pages with handwriting, equations, tables, or drawings in the background"))

    from . import search

    si = search.status()
    if si["sections"] == 0:
        out.append(("warn", "The search index is empty. It fills in on the next check; run 'oso sync' to build it now."), "sync")
    elif si["without_meaning"]:
        out.append(("warn", f"Search covers {si['notes']} notes, but {si['without_meaning']} sections still wait for the search model, which downloads on the next check with an internet connection."))
    else:
        out.append(("ok", f"Search covers {si['notes']} notes ({si['sections']} sections)"))

    from . import sites, skillsync

    with db.connect() as conn:
        for line in sites.problems(conn, cfg):
            out.append(("warn", line.replace("**", "")))
    waiting = skillsync.conflicts()
    if waiting:
        out.append(("warn", f"Oso has new versions of commands you changed ({', '.join(n.removeprefix('oso-') for n in waiting)}). Ask Claude to go through the Oso command updates."))

    if not shutil.which("oso-mcp"):
        out.append(("warn", "The 'oso-mcp' command is not on PATH, so Cowork and Claude Code cannot reach Oso's tools. Run the installer again."))
    return out


def _schedule_missing(cfg, fix: bool, what: str) -> tuple[str, str]:
    """The automatic check is missing: recreate it when fixing, otherwise say how."""
    if not fix:
        return ("warn", f"{what} for the automatic check is not installed, so Oso only updates when you run it. Run 'oso doctor --fix' or 'oso install-task'.")
    from .update import _reschedule

    result = _reschedule(cfg)
    ok = result.startswith("Installed")
    return ("ok" if ok else "warn", f"{what} for the automatic check was missing; recreated it." if ok else result)


_NAMES = {"canvas_feed": "Canvas calendar feed", "canvas_api": "Canvas sign-in", "remarkable_usb": "reMarkable",
          "google_calendar": "Google Calendar", "school_email": "School email", "groupme": "GroupMe"}


def _name(connector: str) -> str:
    return _NAMES.get(connector, connector)


def _ago(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    if minutes < 2:
        return "just now"
    if minutes < 90:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    return f"{hours} hours ago" if hours < 48 else f"{hours // 24} days ago"


def format_report(results: list[tuple[str, str]]) -> str:
    icon = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}
    return "\n".join(f"{icon[s]}  {m}" for s, m in results)
