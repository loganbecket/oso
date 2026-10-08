"""Canvas through the student's own sign-in.

The school does not allow student access keys, so Oso reads Canvas the way his browser does. He signs in
in a small Oso window (`oso connect-canvas`), including any two-step check. If he has given Oso his school
username and password (kept in the operating system's credential store, never in a file), the window fills
them in and submits them itself. The window keeps its own browser memory between sign-ins, so the school's
sign-in page and its two-step service can remember him. When Canvas's dashboard loads, Oso keeps the
signed-in session (the browser cookies for the Canvas address) in the credential store and checks it can
read his course list.

When Canvas stops accepting the session and his username and password are stored, the next check signs in
again on its own, out of sight. Only if the two-step service wants his approval does the window appear, with
a notification to approve it on his phone.

On every check the Canvas reader uses that session. Canvas refreshes it as it is used, and Oso saves the
refreshed copy. When Canvas stops accepting it, the check marks Canvas as needing sign-in, shows one
desktop notification for that expiry (clicking it opens the sign-in window), and keeps a line in
Today.md and `oso doctor` until he signs in again. Each session's start and end are recorded so we
learn how long sessions last at his school.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests

from . import config as cfgmod
from . import secrets

log = logging.getLogger("oso.canvas_session")

SESSION = "canvas_session"
# The cookies Canvas needs, kept if the full set is too long for the credential store (Windows allows ~2.5 KB).
ESSENTIAL = ("canvas_session", "_legacy_normandy_session", "_csrf_token", "log_session_id", "pseudonym_credentials")
USERNAME = "canvas_username"
PASSWORD = "canvas_password"
AUTO_EVERY_MINUTES = 60  # at most one quiet reconnect attempt this often
MAX_STORED = 2400

SCHEMA = """
CREATE TABLE IF NOT EXISTS canvas_sessions (
    id           INTEGER PRIMARY KEY,
    connected_at TEXT NOT NULL,
    expired_at   TEXT,
    notified_at  TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def base_url() -> str | None:
    """The Canvas address: stored when set, otherwise taken from the calendar feed address."""
    base = secrets.get(secrets.CANVAS_BASE_URL)
    if base:
        return base.rstrip("/")
    feed = secrets.get(secrets.CANVAS_FEED_URL)
    if feed:
        u = urlparse(feed.strip())
        if u.scheme and u.netloc:
            return f"https://{u.netloc}"
    return None


def load() -> dict[str, str] | None:
    raw = secrets.get(SESSION)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) and data else None
    except ValueError:
        return None


def save(cookies: dict[str, str]) -> None:
    text = json.dumps(cookies, separators=(",", ":"))
    if len(text) > MAX_STORED:
        text = json.dumps({k: v for k, v in cookies.items() if k in ESSENTIAL}, separators=(",", ":"))
    secrets.set(SESSION, text)


def forget() -> None:
    secrets.delete(SESSION)


def set_login(username: str, password: str) -> None:
    secrets.set(USERNAME, username.strip())
    secrets.set(PASSWORD, password)


def login() -> tuple[str, str] | None:
    u, p = secrets.get(USERNAME), secrets.get(PASSWORD)
    return (u, p) if u and p else None


def forget_login() -> None:
    secrets.delete(USERNAME)
    secrets.delete(PASSWORD)


def verify(base: str, cookies: dict[str, str], timeout: float = 20.0) -> bool:
    """True if the session can read his own profile from Canvas."""
    try:
        r = requests.get(f"{base}/api/v1/users/self", cookies=cookies, timeout=timeout, allow_redirects=False,
                         headers={"Accept": "application/json"})
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    try:
        return "id" in r.json()
    except ValueError:
        return False


# ---- session history and expiry ---------------------------------------------------------------------


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def mark_connected(conn: sqlite3.Connection, now: str | None = None) -> None:
    ensure(conn)
    current = conn.execute("SELECT id FROM canvas_sessions WHERE expired_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if current is None:
        conn.execute("INSERT INTO canvas_sessions (connected_at) VALUES (?)", (now or _now(),))


def mark_expired(conn: sqlite3.Connection, now: str | None = None) -> bool:
    """Record that Canvas refused the session. True only the first time for this session (notify once)."""
    ensure(conn)
    current = conn.execute("SELECT id FROM canvas_sessions WHERE expired_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if current is None:
        return False
    when = now or _now()
    conn.execute("UPDATE canvas_sessions SET expired_at = ?, notified_at = ? WHERE id = ?", (when, when, current["id"]))
    return True


def status(conn: sqlite3.Connection) -> str:
    """'connected', 'needs_sign_in' (a session expired), or 'not_connected' (never signed in, or forgotten)."""
    ensure(conn)
    if load() is None:
        return "not_connected"
    last = conn.execute("SELECT expired_at FROM canvas_sessions ORDER BY id DESC LIMIT 1").fetchone()
    if last is not None and last["expired_at"]:
        return "needs_sign_in"
    return "connected"


def lifetimes(conn: sqlite3.Connection) -> list[float]:
    """Hours each finished session lasted, oldest first."""
    ensure(conn)
    out = []
    for r in conn.execute("SELECT connected_at, expired_at FROM canvas_sessions WHERE expired_at IS NOT NULL ORDER BY id"):
        gap = datetime.fromisoformat(r["expired_at"]) - datetime.fromisoformat(r["connected_at"])
        out.append(round(gap.total_seconds() / 3600, 1))
    return out


SIGN_IN_LINE = "Canvas needs you to sign in again: run 'oso connect-canvas' (or click the notification). Due dates still come from the calendar feed."


# ---- the notification ---------------------------------------------------------------------------------


def notify_sign_in() -> None:
    """One desktop notification. On Windows, clicking it opens the sign-in window."""
    title, body = "Oso", "Canvas needs you to sign in again. Click to sign in."
    try:
        if sys.platform == "win32":
            from winotify import Notification

            launcher = cfgmod.data_dir() / "connect-canvas.cmd"
            launcher.write_text("@echo off\r\noso connect-canvas\r\n", encoding="utf-8")
            n = Notification(app_id="Oso", title=title, msg=body, launch=launcher.as_uri())
            n.show()
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{body}" with title "{title}"'], timeout=10, check=False)
        else:
            subprocess.run(["notify-send", title, body], timeout=10, check=False)
    except Exception as e:  # noqa: BLE001
        log.warning("could not show the Canvas notification: %s", type(e).__name__)


# ---- the sign-in window --------------------------------------------------------------------------------


def _cookies_from(window, host: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for jar in window.get_cookies() or []:
        for name, morsel in jar.items():
            domain = (morsel["domain"] or host).lstrip(".")
            if host == domain or host.endswith("." + domain):
                out[name] = morsel.value
    return out


# Fills the school's sign-in form: the visible password box, and the text box just before it for the username.
# Submits the form the way a click would. Generic: no school's page is named here.
FILL_JS = """
(function (u, p) {
  var visible = function (e) { return e.offsetParent !== null; };
  var pw = Array.prototype.find.call(document.querySelectorAll('input[type=password]'), visible);
  if (!pw) return 'none';
  var boxes = Array.prototype.filter.call(document.querySelectorAll('input'), function (e) {
    var t = (e.getAttribute('type') || 'text').toLowerCase();
    return visible(e) && (t === 'text' || t === 'email') && (e.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  var set = function (el, v) {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  if (boxes.length) set(boxes[boxes.length - 1], u);
  set(pw, p);
  var form = pw.form;
  var button = form && form.querySelector('button[type=submit], input[type=submit], button:not([type])');
  if (button) button.click(); else if (form) form.submit();
  return 'filled';
})(%s, %s)
"""
TWO_STEP_HOSTS = ("duosecurity.com", "duo.com")


def browser_folder():
    """Where the sign-in window keeps its browser memory, so the school's sign-in can remember him."""
    return cfgmod.data_dir() / "canvas-browser"


def sign_in(base: str, timeout_minutes: int = 10, quiet: bool = False) -> dict[str, str] | None:
    """Open the Canvas sign-in page and wait until Canvas is signed in, filling in his stored username and
    password. Returns the session cookies, or None if it didn't finish. `quiet` keeps the window out of sight
    unless he is needed (a two-step approval, or a sign-in the stored password didn't get through), and gives up
    after a few minutes. Raises RuntimeError if no window can be shown."""
    try:
        import webview
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("This computer cannot show the Canvas sign-in window.") from e

    host = urlparse(base).netloc
    found: dict[str, dict[str, str]] = {}
    creds = login()

    def watch(window) -> None:
        import time

        deadline = time.monotonic() + (3 if quiet else timeout_minutes) * 60
        fills, shown, told = 0, not quiet, False
        last, filled_at = "", 0.0

        def show() -> None:
            nonlocal shown
            if not shown:
                window.show()
                shown = True

        while time.monotonic() < deadline:
            time.sleep(1.5)
            try:
                url = window.get_current_url() or ""
            except Exception:  # noqa: BLE001
                return  # window closed
            u = urlparse(url)
            if u.netloc == host and not any(p in u.path for p in ("/login", "/saml", "/sso", "/auth")):
                cookies = _cookies_from(window, host)
                if cookies and verify(base, cookies):
                    found["cookies"] = cookies
                    window.destroy()
                    return
            if any(u.netloc.endswith(h) for h in TWO_STEP_HOSTS):
                show()  # his phone has to approve it
                if quiet and not told:
                    notify("Approve the Duo request on your phone so Oso can reconnect to Canvas.")
                    told = True
                continue
            if url != last:
                last = url
                if creds and fills < 2:
                    try:
                        if window.evaluate_js(FILL_JS % (json.dumps(creds[0]), json.dumps(creds[1]))) == "filled":
                            fills, filled_at = fills + 1, time.monotonic()
                            continue
                    except Exception:  # noqa: BLE001
                        pass
            if not shown and (not creds or fills >= 2 or (fills and time.monotonic() - filled_at > 20)):
                try:
                    if window.evaluate_js("document.querySelector('input[type=password]') ? 'yes' : 'no'") == "yes":
                        show()  # no stored password, or it didn't get through: he signs in himself
                except Exception:  # noqa: BLE001
                    pass
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass

    try:
        folder = browser_folder()
        folder.mkdir(parents=True, exist_ok=True)
        window = webview.create_window("Sign in to Canvas for Oso", f"{base}/login", width=980, height=760, hidden=quiet)
        webview.start(watch, window, private_mode=False, storage_path=str(folder))
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("This computer cannot show the Canvas sign-in window.") from e
    return found.get("cookies")


def notify(body: str) -> None:
    """A plain desktop notification."""
    try:
        if sys.platform == "win32":
            from winotify import Notification

            Notification(app_id="Oso", title="Oso", msg=body).show()
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{body}" with title "Oso"'], timeout=10, check=False)
        else:
            subprocess.run(["notify-send", "Oso", body], timeout=10, check=False)
    except Exception as e:  # noqa: BLE001
        log.warning("could not show a notification: %s", type(e).__name__)


def reconnect_quietly(conn: sqlite3.Connection, now: str | None = None) -> bool:
    """After an expiry, start a quiet sign-in in its own process (the window needs a program's main thread), at most
    once an hour, when his username and password are stored. True if one was started."""
    if login() is None:
        return False
    ensure(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    when = now or _now()
    row = conn.execute("SELECT value FROM meta WHERE key = 'canvas_auto_sign_in'").fetchone()
    if row and (datetime.fromisoformat(when) - datetime.fromisoformat(row["value"])).total_seconds() < AUTO_EVERY_MINUTES * 60:
        return False
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('canvas_auto_sign_in', ?)", (when,))
    from .actions import _start

    _start("connect-canvas", "--quiet")
    return True


def connect(conn: sqlite3.Connection, quiet: bool = False) -> str:
    """The whole `oso connect-canvas` flow. Returns a plain sentence."""
    base = base_url()
    if not base:
        return "Oso doesn't know your Canvas address yet. Set up the Canvas calendar feed first (oso init), then try again."
    try:
        cookies = sign_in(base, quiet=quiet)
    except RuntimeError as e:
        return f"{e} Sign in to Canvas from Windows or macOS."
    if not cookies:
        return "Canvas was not connected: the sign-in window closed before sign-in finished."
    save(cookies)
    mark_connected(conn)
    return "Canvas connected. Oso will read your grades and coursework on every check."
