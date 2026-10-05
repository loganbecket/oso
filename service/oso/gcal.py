"""Deliver urgent changes straight to Google Calendar, with no Claude involved.

`oso connect-calendar --client-file <file>` signs in once through the browser and stores the access in the
credential store. Oso then creates its own calendar named "Oso" and, on every sync, adds an event for each
new urgent change, with reminders, at the item's due time. It only ever touches calendars it created itself
(the `calendar.app.created` permission), so the student's other calendars are out of its reach.

The client file comes from a Google Cloud project with the Calendar API turned on and an OAuth client of type
"Desktop app" (see the README). Set the project's publishing status to "In production"; in "Testing", Google
expires the access after seven days.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import alerts, secrets
from .config import Config
from .db import now_iso

log = logging.getLogger("oso.gcal")

SCOPES = ["https://www.googleapis.com/auth/calendar.app.created"]
API = "https://www.googleapis.com/calendar/v3"
CALENDAR_NAME = "Oso"
TOKEN = "google_calendar_token"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_events (
    alert_id   INTEGER PRIMARY KEY,
    event_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class NotConnected(Exception):
    pass


def connected() -> bool:
    return bool(secrets.get(TOKEN))


def connect(client_file: Path, cfg: Config) -> str:
    """Run the one-time browser sign-in, store the token, and make sure the Oso calendar exists."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline", open_browser=True)
    secrets.set(TOKEN, creds.to_json())
    cal_id = ensure_calendar(_session(), cfg)
    return cal_id


def disconnect() -> None:
    secrets.delete(TOKEN)
    secrets.delete("google_calendar_id")


def _session():
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    raw = secrets.get(TOKEN)
    if not raw:
        raise NotConnected()
    creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        secrets.set(TOKEN, creds.to_json())
    return AuthorizedSession(creds)


def ensure_calendar(session, cfg: Config) -> str:
    cal_id = secrets.get("google_calendar_id")
    if cal_id:
        r = session.get(f"{API}/calendars/{cal_id}")
        if r.ok:
            return cal_id
    r = session.post(f"{API}/calendars", json={"summary": CALENDAR_NAME, "timeZone": cfg.timezone})
    r.raise_for_status()
    cal_id = r.json()["id"]
    secrets.set("google_calendar_id", cal_id)
    return cal_id


def deliver(conn: sqlite3.Connection, cfg: Config, now: datetime, session=None) -> int:
    """Create a calendar event for every urgent change not yet delivered. Returns how many were created."""
    conn.executescript(SCHEMA)
    pend = [a for a in alerts.pending(conn, cfg, now)
            if not (a["deliver_after"] and datetime.fromisoformat(a["deliver_after"]) > now)]  # quiet hours wait
    if not pend:
        return 0
    if session is None:
        session = _session()
    cal_id = ensure_calendar(session, cfg)
    created = 0
    for a in pend:
        if conn.execute("SELECT 1 FROM calendar_events WHERE alert_id = ?", (a["alert_id"],)).fetchone():
            alerts.mark_reported(conn, a["alert_id"])
            continue
        body = event_body(a, cfg, now)
        r = session.post(f"{API}/calendars/{cal_id}/events", json=body)
        r.raise_for_status()
        conn.execute(
            "INSERT INTO calendar_events (alert_id, event_id, created_at) VALUES (?, ?, ?)",
            (a["alert_id"], r.json().get("id", ""), now_iso()),
        )
        alerts.mark_reported(conn, a["alert_id"])
        created += 1
    return created


def event_body(a: dict, cfg: Config, now: datetime) -> dict:
    title = f"Oso: {a['course'] + ': ' if a.get('course') else ''}{a['message']}"
    description = "Noticed by Oso."
    if a.get("url"):
        description += f"\n{a['url']}"
    if a.get("due_at"):
        start = datetime.fromisoformat(a["due_at"])
    else:
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
    end = start + timedelta(minutes=30)
    reminders = [{"method": "popup", "minutes": 24 * 60}, {"method": "popup", "minutes": 120}]
    if start - now < timedelta(hours=2):
        reminders = [{"method": "popup", "minutes": 0}]
    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": cfg.timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": cfg.timezone},
        "reminders": {"useDefault": False, "overrides": reminders},
    }
    if a.get("url"):
        body["source"] = {"title": "Oso", "url": a["url"]}
    return body
