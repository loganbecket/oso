"""The things the student can ask Oso to do, in one place, so a button in the settings window and a request
to Claude run the same code and answer with the same plain sentence.

Long jobs (a full sync, transcription) are started in the background with no window, so neither the
window nor a chat waits on them; their results show in the briefing and the status panel.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config as cfgmod
from . import db


def _windowless_python() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if sys.platform == "win32" and w.exists() else exe)


def _start(*args: str) -> None:
    """Run `python -m oso <args>` in the background, detached from whoever asked."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([_windowless_python(), "-m", "oso", *args], **kwargs)


def status() -> list[dict]:
    """The status panel's lines: {status: ok|warn|fail, text, action}."""
    import re

    from . import doctor

    lines = doctor.checks(fix=False)
    for c in lines:
        if c["action"]:  # the button beside the line does what the terminal hint says
            text = re.sub(r"\s*\(run with --fix[^)]*\)|[;,]?\s*\b[Rr]un 'oso [^']*'[^.]*\.", "", c["text"]).strip()
            c["text"] = text + "." if text[-1:].isalnum() else text
    return lines


def health_check(fix: bool = False) -> str:
    from . import doctor

    lines = doctor.checks(fix=fix)
    problems = [c for c in lines if c["status"] != "ok"]
    if not problems:
        return "Everything checks out." + (" Fixed what could be fixed." if fix else "")
    return ("Fixed what could be fixed. Still needs attention:\n" if fix else "Needs attention:\n") + "\n".join(f"- {c['text']}" for c in problems)


def sync_now() -> str:
    _start("sync")
    return "Oso is checking everything now, in the background. It takes a few minutes; the briefing and the status panel show the result."


def transcribe_now() -> str:
    _start("transcribe")
    return "Oso is having Claude read waiting handwritten pages now, in the background."


def update_oso() -> str:
    from . import update

    return update.run(cfgmod.load())


def backup_now() -> str:
    from . import backup, lock

    cfg = cfgmod.load()
    if not cfg.backup_folder:
        return "No backup folder is set. Set one under Settings, then try again."
    with lock.held(wait_seconds=5) as got:
        if not got:
            return "Another Oso task is running; try again in a few minutes."
        with db.connect() as conn:
            r = backup.run(cfg, conn, datetime.now(cfg.tz), force=True, budget=10**6)
    return r.get("skipped") or f"Backed up {r['copied']} changed files and Oso's records."


def connect_canvas() -> str:
    from . import canvas_session

    with db.connect() as conn:
        return canvas_session.connect(conn)


def disconnect_canvas() -> str:
    from . import canvas_session

    canvas_session.forget()
    return "Oso forgot your Canvas sign-in. Due dates still come from the calendar feed."


def connect_email(client_file=None) -> str:
    from . import mail

    try:
        addr = mail.connect(client_file)
    except Exception as e:  # noqa: BLE001
        if "client file" in str(e):
            return str(e)
        return f"Email didn't connect ({e})."
    return f"Connected {addr}. Oso reads new email there on every check; nothing is ever sent or changed."


def disconnect_email() -> str:
    from . import mail

    mail.disconnect()
    return "Oso forgot the email connection."


def connect_groupme(token: str) -> str:
    from . import groupme

    try:
        name = groupme.connect(token)
    except Exception:  # noqa: BLE001
        return "GroupMe didn't accept that access token. Copy it again from dev.groupme.com (Access Token, top right)."
    return f"Connected GroupMe as {name}. Oso reads your groups on every check; mute any that never matter."


def disconnect_groupme() -> str:
    from . import groupme

    groupme.disconnect()
    return "Oso forgot the GroupMe connection."


def quizzes(limit: int = 200) -> list[dict]:
    """Every quiz, newest first, for the Quizzes tab."""
    from . import profile

    with db.connect() as conn:
        return profile.recent_quizzes(conn, limit=limit)


def open_quiz(quiz_id: int) -> str:
    """Open a quiz in the quiz window: to take it if he hasn't, or read-only with the answers if he has."""
    from . import profile, quizwin

    with db.connect() as conn:
        profile.ensure(conn)
        quiz = conn.execute("SELECT submitted_at FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        return f"There is no quiz {quiz_id}."
    quizwin.launch(quiz_id)
    return "The quiz is opening, read-only, with the right answers shown." if quiz["submitted_at"] else "The quiz is opening for you to take."


def books() -> str:
    from . import books as bk

    rows = bk.progress(cfgmod.load())
    if not rows:
        return "No books yet. Put a book's PDF or EPUB in a course's Books folder, or its scans in Books/<title>/Scans."
    out = []
    for b in rows:
        state = b["error"] or ("read" if b["total"] and b["done"] >= b["total"] else f"{b['done']} of {b['total'] or '?'} pages read so far")
        out.append(f"{b['book']} ({b['course']}): {state}" + (f"; {b['poor']} pages waiting for Claude" if b["poor"] else ""))
    return "\n".join(out)


def reread_book(title: str) -> str:
    from . import books as bk

    return bk.reprocess(cfgmod.load(), title)


def websites(check: bool = False) -> str:
    from . import sites

    cfg = cfgmod.load()
    with db.connect() as conn:
        if check:
            sites.check(cfg, conn, force=True)
        rows = sites.status(conn, cfg)
    if not rows:
        return "No instructor websites are followed yet. Tell Claude about one, or add it below."
    names = {c.code: c.name for c in cfg.courses}
    return "\n".join(f"{names.get(r['course'], r['course'])}: {r['site']} ({r['status'].replace('_', ' ')}; {r['pages']} pages, {r['files']} files)" for r in rows)


def add_website(course: str, url: str) -> str:
    from . import courses, sites

    try:
        courses.update(cfgmod.load(), course, add_site=url)
    except ValueError as e:
        return str(e)
    return f"Following {sites.normalize(url)}; it is checked on the next check."


def remove_website(course: str, url: str) -> str:
    from . import courses

    try:
        courses.update(cfgmod.load(), course, remove_site=url)
    except ValueError as e:
        return str(e)
    return f"No longer following {url}."


# ---- the settings window, opened from Claude --------------------------------------------------------


def raise_request_path() -> Path:
    return cfgmod.data_dir() / "settings.raise"


def window_pid_path() -> Path:
    return cfgmod.data_dir() / "settings.pid"


def open_settings() -> str:
    """Open the settings window on this computer, or bring it to the front if it is already open."""
    from .lock import _alive

    pid_file = window_pid_path()
    try:
        pid = int(pid_file.read_text().strip() or 0)
    except (OSError, ValueError):
        pid = 0
    if pid and _alive(pid):
        raise_request_path().write_text(str(datetime.now().timestamp()), encoding="utf-8")
        return "The Oso window is already open; it's been brought to the front."
    _start("settings")
    return "The Oso window is opening on your computer."
