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
    s = sub.add_parser("quiz", help="open the quiz window again for a quiz Claude gave you")
    s.add_argument("quiz_id", nargs="?", type=int, help="the quiz number (default: the latest one not yet submitted)")
    s = sub.add_parser("profile", help="show what the learner profile has recorded")
    s.add_argument("--raw", action="store_true", help="every recent quiz with each question and answer")
    s.add_argument("--delete-quiz", type=int, metavar="N", help="delete quiz N completely (asks first)")
    s = sub.add_parser("sites", help="instructors' websites Oso follows for new materials")
    s.add_argument("--add", nargs=2, metavar=("COURSE", "URL"), help="follow a page for a course")
    s.add_argument("--remove", nargs=2, metavar=("COURSE", "URL"), help="stop following a page")
    s.add_argument("--check", action="store_true", help="check every followed page now")
    s = sub.add_parser("backup", help="back up the vault and Oso's records now (to the folder in settings)")
    s.add_argument("--set-folder", metavar="PATH", help="set the backup folder (checked first); '' turns backups off")
    s = sub.add_parser("restore", help="bring the vault and Oso's records back from a backup folder")
    s.add_argument("--from", dest="source", metavar="PATH", help="the backup folder (default: the one in settings)")
    s.add_argument("--date", metavar="YYYY-MM-DD", help="Oso's records as they were that day (the vault is always the latest)")
    sub.add_parser("watch", help="take in new course files as soon as they arrive (started automatically at sign-in)")
    sub.add_parser("fresh-start", help="delete everything in the vault and Oso's records and start fresh, keeping your settings")
    s = sub.add_parser("reset-skills", help="put back Oso's version of its commands' instructions (all, or the ones named), discarding your edits")
    s.add_argument("names", nargs="*", help="commands to reset, e.g. oso-summarize (default: all)")
    s = sub.add_parser("connect-calendar", help="let Oso put urgent changes on its own Google calendar")
    s.add_argument("--client-file", required=True, help="the OAuth client file downloaded from Google Cloud")
    s = sub.add_parser("connect-canvas", help="sign in to Canvas so Oso can read your grades and coursework")
    s.add_argument("--quiet", action="store_true", help="sign in out of sight with the stored username and password (used by the check)")
    sub.add_parser("disconnect-canvas", help="forget the Canvas sign-in")
    s = sub.add_parser("books", help="show how far Oso has read each textbook")
    s.add_argument("--reprocess", metavar="TITLE", help="read a book again from the start")
    s = sub.add_parser("canvas", help="show what Oso has read from Canvas")
    s.add_argument("--raw", action="store_true", help="every course and assignment with its score")
    sub.add_parser("disconnect-calendar", help="stop Oso writing to Google Calendar and forget its access")
    s = sub.add_parser("connect-email", help="let Oso read the Gmail account your school email is forwarded to (read-only)")
    s.add_argument("--client-file", help="the OAuth client file from Google Cloud (only if Oso asks for it)")
    sub.add_parser("disconnect-email", help="stop reading email and forget its access")
    s = sub.add_parser("connect-tasks", help="keep your tasks in a Google Tasks list named Oso, on your phone")
    s.add_argument("--client-file", help="the OAuth client file from Google Cloud (only if Oso asks for it)")
    sub.add_parser("disconnect-tasks", help="stop using Google Tasks and forget its access")
    sub.add_parser("connect-groupme", help="let Oso read your GroupMe groups, with the access token from dev.groupme.com")
    sub.add_parser("disconnect-groupme", help="stop reading GroupMe and forget the token")
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
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001  a sentence for the student; the detail goes to errors.log
        sync._record_failure(args.cmd or "oso")
        print(f"Oso couldn't finish '{args.cmd}': {sync.plain_error(e)}", file=sys.stderr)
        return 1


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

    if args.cmd == "connect-email":
        from . import actions

        print("A browser window will open. Sign in with the Gmail account your school email is forwarded to, and allow Oso to read it.")
        print(actions.connect_email(Path(args.client_file).expanduser() if args.client_file else None))
        return 0

    if args.cmd == "connect-tasks":
        from . import actions

        print("A browser window will open. Sign in with the Google account for Oso, and allow it to manage your tasks.")
        print(actions.connect_tasks(Path(args.client_file).expanduser() if args.client_file else None))
        return 0

    if args.cmd == "disconnect-tasks":
        from . import actions

        print(actions.disconnect_tasks())
        return 0

    if args.cmd == "disconnect-email":
        from . import actions

        print(actions.disconnect_email())
        return 0

    if args.cmd == "connect-groupme":
        import getpass

        from . import actions

        print("Sign in at dev.groupme.com, click Access Token at the top right, and copy it.")
        print(actions.connect_groupme(getpass.getpass("Paste the access token (it won't show): ")))
        return 0

    if args.cmd == "disconnect-groupme":
        from . import actions

        print(actions.disconnect_groupme())
        return 0

    if args.cmd == "connect-canvas":
        from . import canvas_session

        with db.connect() as conn:
            result = canvas_session.connect(conn, quiet=args.quiet)
            if args.quiet and not result.startswith("Canvas connected"):
                canvas_session.notify_sign_in()  # the quiet try didn't finish: ask him, as before
            elif not args.quiet:
                canvas_session.notify(result)  # opened from the Oso window, where nothing shows what was printed
        print(result)
        return 0

    if args.cmd == "disconnect-canvas":
        from . import canvas_session

        canvas_session.forget()
        print("Oso forgot your Canvas sign-in. Due dates still come from the calendar feed.")
        return 0

    if args.cmd == "books":
        from . import books

        if args.reprocess:
            print(books.reprocess(cfg, args.reprocess))
            return 0
        rows = books.progress(cfg)
        if not rows:
            print("No books yet. Put a book's PDF or EPUB in a course's Books folder, or its scans in Books/<title>/Scans.")
        for b in rows:
            state = b["error"] or ("done" if b["total"] and b["done"] >= b["total"] else f"{b['done']} of {b['total'] or '?'} pages read")
            print(f"{b['book']} ({b['course']}): {state}" + (f"; {b['poor']} pages read poorly" if b["poor"] else ""))
        return 0

    if args.cmd == "canvas":
        from . import canvas_store

        with db.connect() as conn:
            print(canvas_store.raw_dump(conn, cfg))
        return 0

    if args.cmd == "disconnect-calendar":
        from . import gcal

        gcal.disconnect()
        print("Disconnected. Oso will no longer write to Google Calendar. The Oso calendar itself is left as is.")
        return 0

    if args.cmd == "quiz":
        from . import profile, quizwin

        quiz_id = args.quiz_id
        if quiz_id is None:
            with db.connect() as conn:
                waiting = [q for q in profile.recent_quizzes(conn, limit=20) if q["status"] == "handed_out"]
            if not waiting:
                print("There is no quiz waiting. Ask Claude for one in the chat.")
                return 0
            quiz_id = waiting[0]["quiz_id"]
        quizwin.run(quiz_id)
        return 0

    if args.cmd == "profile":
        from . import profile

        if args.delete_quiz is not None:
            if input(f"Delete quiz {args.delete_quiz} and all its results for good? Type yes: ").strip().lower() != "yes":
                print("Nothing was deleted.")
                return 0
            with db.connect() as conn:
                try:
                    print(profile.delete_quiz(conn, cfg, args.delete_quiz))
                except profile.ProfileError as e:
                    print(e)
                    return 1
            return 0
        with db.connect() as conn:
            print(profile.raw_dump(conn))
        return 0

    if args.cmd == "sites":
        from . import courses, sites

        try:
            if args.add:
                courses.update(cfg, args.add[0], add_site=args.add[1])
                print(f"Following {sites.normalize(args.add[1])} for {args.add[0]}; it is checked on the next check (or run 'oso sites --check').")
                return 0
            if args.remove:
                courses.update(cfg, args.remove[0], remove_site=args.remove[1])
                print(f"No longer following {args.remove[1]}.")
                return 0
        except ValueError as e:
            print(e)
            return 1
        with db.connect() as conn:
            if args.check:
                print(sites.check(cfg, conn, force=True))
            rows = sites.status(conn, cfg)
        if not rows:
            print("No instructor websites followed yet. Tell Claude about one, or run: oso sites --add <course> <address>")
        for r in rows:
            print(f"{r['course']}: {r['site']} ({r['status']}; {r['pages']} pages, {r['files']} files)")
        return 0

    if args.cmd == "backup":
        from . import backup

        if args.set_folder is not None:
            if not args.set_folder.strip():
                cfg.backup_folder = None
                cfgmod.save(cfg)
                print("Backups are off.")
                return 0
            try:
                backup.check_folder(Path(args.set_folder))
            except backup.BackupError as e:
                print(e)
                return 1
            cfg.backup_folder = args.set_folder
            cfgmod.save(cfg)
            print(f"Backups will go to {args.set_folder} every night.")
            return 0
        if not cfg.backup_folder:
            print("No backup folder is set. Run 'oso backup --set-folder <folder>' or set one in 'oso settings'.")
            return 1
        from datetime import datetime as _dt

        from . import lock

        with lock.held() as got, db.connect() as conn:
            if not got:
                print("Another Oso task is running; try again in a few minutes.")
                return 1
            r = backup.run(cfg, conn, _dt.now(cfg.tz), force=True, budget=10**6)
        if "skipped" in r:
            print(r["skipped"])
            return 1
        print(f"Backed up {r['copied']} changed files and Oso's records to {cfg.backup_folder}"
              + (f"; {r['removed']} deleted files kept under Removed" if r["removed"] else "") + ".")
        return 0

    if args.cmd == "restore":
        from . import backup

        source = args.source or cfg.backup_folder
        if not source:
            print("Say where the backup is: oso restore --from <folder>")
            return 1
        try:
            lines = backup.restore(cfg, Path(source), day=args.date)
        except backup.BackupError as e:
            if "already has notes" not in str(e):
                print(e)
                return 1
            if input(f"{e} Type yes to write over it: ").strip().lower() != "yes":
                print("Nothing was restored.")
                return 0
            lines = backup.restore(cfg, Path(source), day=args.date, overwrite=True)
        for line in lines:
            print(line)
        return 0

    if args.cmd == "watch":
        from . import watch

        watch.main()
        return 0

    if args.cmd == "fresh-start":
        from . import fresh

        try:
            fresh.check_vault(cfg.vault)
        except fresh.NotAVault as e:
            print(f"Stopped: {e} Nothing was deleted.")
            return 1
        print(f"This deletes everything in {cfg.vault} except Obsidian's settings and your textbooks, plus every course, deadline,")
        print("grade, quiz result, and transcription Oso has recorded. There is no backup. Your settings and connections are kept.")
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
