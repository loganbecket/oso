"""Command line: oso init | sync | today | health | add-course | install-task."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import config as cfgmod
from . import db, secrets, sync, today


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="oso", description="Oso study assistant service")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="point Oso at your vault and Canvas calendar feed")
    s.add_argument("--vault", required=True, help="path to your Obsidian vault")
    s.add_argument("--timezone", default="America/New_York")
    s.add_argument("--canvas-feed-url", help="the Calendar Feed URL from Canvas (asked for if omitted)")
    s.add_argument("--canvas-url", help="your school's Canvas address, e.g. https://school.instructure.com (only with a token)")
    s.add_argument("--canvas-token", help="a Canvas access token, if your school allows students to create one")

    s = sub.add_parser("add-course", help="register a course")
    s.add_argument("code", help="code as Canvas shows it, e.g. MATH-101-001")
    s.add_argument("name", help="short name, e.g. Calculus I")
    s.add_argument("--term", help='term, e.g. "2026 Fall"; the folder becomes Courses/<term>/<name>')
    s.add_argument("--related", nargs="*", default=None, help="codes or names of earlier courses this one builds on")

    sub.add_parser("sync", help="pull every source and rewrite Today.md")
    sub.add_parser("today", help="rewrite Today.md from what is already stored")
    sub.add_parser("health", help="show when each source last synced")
    s = sub.add_parser("doctor", help="check the installation and explain anything wrong")
    s.add_argument("--fix", action="store_true", help="create missing vault folders")
    s = sub.add_parser("set-remarkable-folder", help="the tablet folder that holds the course folders (blank = the tablet's top level)")
    s.add_argument("folder", nargs="?", default="")
    s = sub.add_parser("set-drive-folder", help="mirror a Google Drive folder (synced by Drive for Desktop) into a course")
    s.add_argument("code", help="course code")
    s.add_argument("path", help="local path of the Drive folder")
    s = sub.add_parser("install-task", help="schedule the sync (Windows scheduled task, macOS launch agent, or Linux systemd timer)")
    s.add_argument("--every", type=int, default=None, help="minutes between runs (default: the saved setting, 15)")
    sub.add_parser("settings", help="open the settings window")
    s = sub.add_parser("update", help="install the newest Oso on your update channel (set in oso settings; stable by default)")
    s.add_argument("--version", help="install this exact version (e.g. v0.1.0) or commit, for rolling back")
    s.add_argument("--installed", help=argparse.SUPPRESS)  # set by the installers after they install
    sub.add_parser("fresh-start", help="delete everything in the vault and Oso's records and start fresh, keeping your settings")
    s = sub.add_parser("reset-skills", help="put back Oso's version of its commands' instructions (all, or the ones named), discarding your edits")
    s.add_argument("names", nargs="*", help="commands to reset, e.g. oso-summarize (default: all)")
    s = sub.add_parser("connect-calendar", help="let Oso put urgent changes on its own Google calendar")
    s.add_argument("--client-file", required=True, help="the OAuth client file downloaded from Google Cloud")
    sub.add_parser("disconnect-calendar", help="stop Oso writing to Google Calendar and forget its access")
    s = sub.add_parser("transcribe", help="turn queued handwritten pages into notes, one page per Claude Code call")
    s.add_argument("--model", help="override the model from settings (sonnet, opus, ...)")
    s.add_argument("--limit", type=int, default=200, help="at most this many pages")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return _dispatch(args)
    except cfgmod.ConfigError as e:
        print(e, file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "init":
        vault = Path(args.vault).expanduser().resolve()
        if not vault.is_dir():
            print(f"{vault} is not a folder. Create the vault in Obsidian first.", file=sys.stderr)
            return 2
        cfg = cfgmod.Config(vault=vault, timezone=args.timezone)
        try:
            cfg = cfgmod.load()
            cfg.vault, cfg.timezone = vault, args.timezone
        except cfgmod.ConfigError:
            pass
        path = cfgmod.save(cfg)
        url = args.canvas_feed_url
        if url is None:
            url = input("Canvas Calendar Feed URL (Canvas > Calendar > Calendar Feed, or leave blank): ").strip()
        if url:
            secrets.set(secrets.CANVAS_FEED_URL, url)
        if args.canvas_url and args.canvas_token:
            secrets.set(secrets.CANVAS_BASE_URL, args.canvas_url)
            secrets.set(secrets.CANVAS_TOKEN, args.canvas_token)
        for sub in ("Clippings", "Courses", "Oso"):
            (vault / sub).mkdir(parents=True, exist_ok=True)
        print(f"Saved settings to {path}. Feed URL stored in the credential manager." if url else f"Saved settings to {path}.")
        return 0

    cfg = cfgmod.load()

    if args.cmd == "add-course":
        from . import courses

        try:
            c = courses.register(cfg, args.code, args.name, term=args.term, related=args.related)
        except ValueError as e:
            print(e)
            return 1
        print(f"Added {c.name} ({c.code}); vault folder Courses/{c.folder}")
        return 0

    if args.cmd == "sync":
        results = sync.run(cfg)
        for name, r in results.items():
            print(f"{name}: {r}")
        print(f"Wrote {cfg.vault / 'Today.md'}")
        return 0

    if args.cmd == "today":
        with db.connect() as conn:
            path = today.write(conn, cfg, datetime.now(cfg.tz))
        print(f"Wrote {path}")
        return 0

    if args.cmd == "health":
        with db.connect() as conn:
            rows = db.connector_health(conn)
        if not rows:
            print("No sources have synced yet.")
        for r in rows:
            state = "ok" if r["last_ok"] else f"failed: {r['last_error']}"
            print(f"{r['connector']}: last run {r['last_run']} ({state}); last success {r['last_success']}")
        return 0

    if args.cmd == "doctor":
        from . import doctor

        results = doctor.run(fix=args.fix)
        print(doctor.format_report(results))
        return 1 if any(s == "fail" for s, _ in results) else 0

    if args.cmd == "set-remarkable-folder":
        cfg.remarkable_folder = args.folder.strip() or None
        cfgmod.save(cfg)
        where = f"inside the tablet folder '{cfg.remarkable_folder}'" if cfg.remarkable_folder else "at the tablet's top level"
        print(f"Looking for course folders {where}: " + ", ".join(c.folder for c in cfg.courses))
        return 0

    if args.cmd == "set-drive-folder":
        c = cfg.course_for(args.code)
        if c is None:
            print(f"No course with code {args.code}. Add it first.", file=sys.stderr)
            return 2
        p = Path(args.path).expanduser().resolve()
        if not p.is_dir():
            print(f"{p} is not a folder.", file=sys.stderr)
            return 2
        c.drive_folder = str(p)
        cfgmod.save(cfg)
        print(f"{c.name} will mirror {p} into Courses/{c.folder}/Drive on every sync.")
        return 0

    if args.cmd == "transcribe":
        from . import transcribe

        with db.connect() as conn:
            try:
                counts = transcribe.run(conn, cfg, limit=args.limit, model=args.model)
            except transcribe.ClaudeMissing as e:
                print(e, file=sys.stderr)
                return 2
        print(f"Transcribed {counts['pages']} page(s) into {counts['notes']} note(s); {counts['low_confidence']} low confidence, {counts['failed']} failed.")
        if counts["pages"]:
            from . import today as todaymod

            with db.connect() as conn:
                todaymod.write(conn, cfg, datetime.now(cfg.tz))
        return 0

    if args.cmd == "connect-calendar":
        from . import gcal

        client = Path(args.client_file).expanduser()
        if not client.is_file():
            print(f"{client} is not a file. Download the OAuth client file from Google Cloud first (see the README).", file=sys.stderr)
            return 2
        print("A browser window will open. Sign in with your Google account and allow access.")
        gcal.connect(client, cfg)
        print("Connected. Oso created a calendar named 'Oso' and will put urgent changes on it.")
        return 0

    if args.cmd == "disconnect-calendar":
        from . import gcal

        gcal.disconnect()
        print("Disconnected. Oso will no longer write to Google Calendar. The Oso calendar itself is left as is.")
        return 0

    if args.cmd == "fresh-start":
        from . import fresh

        try:
            fresh.check_vault(cfg.vault)
        except fresh.NotAVault as e:
            print(f"Stopped: {e} Nothing was deleted.")
            return 1
        print(f"This deletes everything in {cfg.vault} except Obsidian's settings, plus every course, deadline,")
        print("grade, and transcription Oso has recorded. There is no backup. Your settings and connections are kept.")
        print("Quit the Claude app first.")
        if input("Type yes to start fresh: ").strip().lower() != "yes":
            print("Nothing was deleted.")
            return 0
        for line in fresh.run(cfg):
            print(line)
        print("Running a first check...")
        results = sync.run(cfgmod.load())
        feed = results.get("canvas_feed")
        print(f"Canvas: {feed}" if feed is not None else "Canvas: not connected")
        print("Fresh start done. Reopen the Claude app, then set up each course with /create-course.")
        return 0

    if args.cmd == "reset-skills":
        from . import skillsync

        print(skillsync.reset(cfg, args.names or None))
        return 0

    if args.cmd == "update":
        from . import update

        print(update.record(cfg, args.installed) if args.installed else update.run(cfg, version=args.version))
        return 0

    if args.cmd == "settings":
        from .settings_gui import open_settings

        open_settings(cfg)
        return 0

    if args.cmd == "install-task":
        if args.every:
            cfg.sync_interval_minutes = args.every
            cfgmod.save(cfg)
        args.every = cfg.sync_interval_minutes
        if sys.platform == "win32":
            from .install_windows import install_task

            print(install_task(every_minutes=args.every))
        elif sys.platform == "darwin":
            from .install_macos import install_agent

            print(install_agent(every_minutes=args.every))
        else:
            from .install_linux import install_timer

            print(install_timer(every_minutes=args.every))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
