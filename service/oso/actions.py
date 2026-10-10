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
    """Open the Canvas sign-in window in its own process: the window has to run on a program's main thread, and the
    Oso window (and Claude's tools) call this from a background one."""
    _start("connect-canvas")
    return ("The Canvas sign-in window is opening. Sign in as usual; it closes by itself when you're in. "
            "Then press Refresh to see Canvas connected.")


def set_canvas_login(username: str, password: str) -> str:
    from . import canvas_session

    if not username.strip() or not password:
        return "Nothing changed: both the username and the password are needed."
    canvas_session.set_login(username, password)
    return ("Saved in your computer's credential store. The Canvas sign-in window fills them in from now on, and when Canvas "
            "logs you out Oso signs in again on its own; you'll only need to approve Duo on your phone.")


def disconnect_canvas() -> str:
    from . import canvas_session

    canvas_session.forget()
    canvas_session.forget_login()
    return "Oso forgot your Canvas sign-in, username, and password. Due dates still come from the calendar feed."


def connect_email(client_file=None) -> str:
    from . import mail

    try:
        addr = mail.connect(client_file)
    except Exception as e:  # noqa: BLE001
        if "client file" in str(e):
            return str(e)
        return f"Email didn't connect ({e})."
    return (f"Connected {addr}. Oso reads new email there on every check and changes nothing. The one thing it can send "
            "is feedback about Oso, only when he asks, only to whoever builds Oso.")


def connect_tasks(client_file=None) -> str:
    from . import tasks

    try:
        tasks.connect(client_file)
    except Exception as e:  # noqa: BLE001
        if "client file" in str(e):
            return str(e)
        return f"Google Tasks didn't connect ({e})."
    return "Connected Google Tasks. His tasks are in the list named Oso, on his phone and in Google Calendar."


def disconnect_tasks() -> str:
    from . import tasks

    tasks.disconnect()
    return "Oso forgot the Google Tasks connection. His tasks are still kept in Oso."


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


def grades() -> list[dict]:
    """Each class's grade from Canvas, lowest first, for the Grades tab."""
    from . import canvas_store

    with db.connect() as conn:
        return canvas_store.grade_table(conn, cfgmod.load())


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


def retake_quiz(quiz_id: int) -> str:
    """The same questions again, once, opened in the quiz window."""
    from . import profile, quizwin

    with db.connect() as conn:
        try:
            new_id = profile.retake(conn, cfgmod.load(), quiz_id)
        except profile.ProfileError as e:
            return str(e)
    quizwin.launch(new_id)
    return "The retake is opening. Right answers on a retake don't count toward where you stand (you've seen them); wrong ones do."


def new_version(quiz_id: int) -> str:
    from . import quizwin

    quizwin.launch_new_version(quiz_id)
    return "Claude is writing a new version in the background; the quiz window opens when it's ready."


def delete_quiz(quiz_id: int) -> str:
    """Remove a quiz for good, in any state: it no longer counts anywhere."""
    from . import profile

    with db.connect() as conn:
        try:
            return profile.delete_quiz(conn, cfgmod.load(), quiz_id)
        except profile.ProfileError as e:
            return str(e)


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


def saved_pages() -> str:
    cfg = cfgmod.load()
    if not cfg.saved_pages:
        return "No saved pages yet. Tell Claude about one (\"save the dining hall hours page\"), or add it below."
    return "\n".join(f"{p.name}: {p.about} ({p.url})" for p in cfg.saved_pages)


def save_page(name: str, url: str, about: str) -> str:
    from . import saved_pages as pages

    try:
        p = pages.save(cfgmod.load(), name, url, about)
    except ValueError as e:
        return str(e)
    return f"Saved {p.name}. Claude starts there when you ask about {p.about}."


def forget_page(name: str) -> str:
    from . import saved_pages as pages

    return f"Forgot {name}." if pages.forget(cfgmod.load(), name) else f"No saved page called {name!r}."


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
