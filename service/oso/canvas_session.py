"""Canvas through the student's own sign-in.

The school does not allow student access keys, so Oso reads Canvas the way his browser does. He signs in
once in a small Oso window (`oso connect-canvas`), including any two-step check; Oso never sees his
password. When Canvas's dashboard loads, Oso keeps the signed-in session (the browser cookies for the
Canvas address) in the operating system's credential store and checks it can read his course list.

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
ESSENTIAL = ("canvas_session", "_legacy_normandy_session", "_csrf_token", "log_session_id")
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


def sign_in(base: str, timeout_minutes: int = 10) -> dict[str, str] | None:
    """Open the Canvas sign-in page in a small window and wait until Canvas is signed in. Returns the
    session cookies, or None if the window was closed first. Raises RuntimeError if no window can be shown."""
    try:
        import webview
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("This computer cannot show the Canvas sign-in window.") from e

    host = urlparse(base).netloc
    found: dict[str, dict[str, str]] = {}

    def watch(window) -> None:
        import time

        deadline = time.monotonic() + timeout_minutes * 60
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
        try:
            window.destroy()
        except Exception:  # noqa: BLE001
            pass

    try:
        window = webview.create_window("Sign in to Canvas for Oso", f"{base}/login", width=980, height=760)
        webview.start(watch, window, private_mode=False)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("This computer cannot show the Canvas sign-in window.") from e
    return found.get("cookies")


def connect(conn: sqlite3.Connection) -> str:
    """The whole `oso connect-canvas` flow. Returns a plain sentence."""
    base = base_url()
    if not base:
        return "Oso doesn't know your Canvas address yet. Set up the Canvas calendar feed first (oso init), then try again."
    try:
        cookies = sign_in(base)
    except RuntimeError as e:
        return f"{e} Sign in to Canvas from Windows or macOS."
    if not cookies:
        return "Canvas was not connected: the sign-in window closed before sign-in finished."
    save(cookies)
    mark_connected(conn)
    return "Canvas connected. Oso will read your grades and coursework on every check."
