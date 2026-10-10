"""GroupMe: on every check, read the new messages in each of the student's groups.

He signs in at dev.groupme.com, copies his access token, and gives it to Oso once (`oso connect-groupme`, or
the Oso window); it is kept in the credential store. Every group is read unless he mutes it. Only group chats
are read, never direct messages, and his own messages are skipped. New messages go through the same picking-out
as email (`messages.py`), one batch per group, with the group's name as context. Pictures posted in a message
(event flyers, mostly) are read by Claude first, and their words join the message's text.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta

import requests

from . import messages, secrets
from .config import Config

log = logging.getLogger("oso.groupme")

API = "https://api.groupme.com/v3"
TOKEN = "groupme_token"
USER = "groupme_user_id"
FIRST_DAYS = 2  # the first read of a group looks back this far
PAGES_PER_CHECK = 5
PICTURES = "https://i.groupme.com/"  # GroupMe's own picture service; nothing else is fetched
PICTURES_PER_MESSAGE = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS groupme_groups (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    last_id     TEXT,
    seen_at     TEXT
);
"""


def connected() -> bool:
    return bool(secrets.get(TOKEN))


class _Api:
    """GroupMe's API with the token attached; replaced by recorded responses in tests."""

    def __init__(self, token: str):
        self.token = token

    def get(self, path: str, **params) -> tuple[int, dict | None]:
        r = requests.get(f"{API}{path}", params=params, headers={"X-Access-Token": self.token}, timeout=30)
        if r.status_code == 304:
            return 304, None
        if r.status_code == 401:
            raise messages.NotConnected("GroupMe no longer accepts the access token; connect GroupMe again")
        r.raise_for_status()
        return r.status_code, r.json().get("response")


def connect(token: str, api=None) -> str:
    """Check the token works and keep it. Returns his GroupMe name."""
    token = token.strip()
    api = api or _Api(token)
    _, me = api.get("/users/me")
    secrets.set(TOKEN, token)
    secrets.set(USER, str(me.get("id") or me.get("user_id") or ""))
    return me.get("name") or "you"


def disconnect() -> None:
    secrets.delete(TOKEN)
    secrets.delete(USER)


def groups(conn: sqlite3.Connection) -> list[dict]:
    """The groups Oso has seen, for the settings window and Claude."""
    from . import schema

    schema.apply(conn)
    return [dict(r) for r in conn.execute("SELECT id, name FROM groupme_groups ORDER BY name COLLATE NOCASE")]


def fetch(conn: sqlite3.Connection, cfg: Config, now: datetime, api=None) -> dict[str, int]:
    """Store new messages from every group he hasn't muted."""
    messages.ensure(conn)
    if api is None:
        token = secrets.get(TOKEN)
        if not token:
            raise messages.NotConnected("GroupMe is not connected")
        api = _Api(token)
    me = secrets.get(USER) or ""
    _, listed = api.get("/groups", per_page=100, omit="memberships")
    counts = {"kept": 0, "groups": 0, "muted": 0}
    muted = {m.lower() for m in cfg.muted_groups}
    for g in listed or []:
        gid, name = str(g["id"]), g.get("name") or "a group"
        conn.execute(
            "INSERT INTO groupme_groups (id, name, seen_at) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name, seen_at = excluded.seen_at",
            (gid, name, now.isoformat(timespec="minutes")),
        )
        if gid.lower() in muted or name.lower() in muted:
            counts["muted"] += 1
            continue
        counts["groups"] += 1
        last = conn.execute("SELECT last_id FROM groupme_groups WHERE id = ?", (gid,)).fetchone()["last_id"]
        new = _new_messages(api, gid, last, now)
        for m in new:
            if str(m.get("user_id")) == me or (m.get("sender_type") == "system" and not _event_text(m)):
                continue
            messages.store(conn, record(m, gid, name))
            counts["kept"] += 1
        if new:
            conn.execute("UPDATE groupme_groups SET last_id = ? WHERE id = ?", (str(new[-1]["id"]), gid))
    return counts


def _new_messages(api, gid: str, last: str | None, now: datetime) -> list[dict]:
    """Messages after the last one seen, oldest first. The first time, only the last couple of days."""
    if not last:
        status, body = api.get(f"/groups/{gid}/messages", limit=50)
        recent = sorted((body or {}).get("messages", []), key=lambda m: m.get("created_at", 0))
        cutoff = (now - timedelta(days=FIRST_DAYS)).timestamp()
        kept = [m for m in recent if m.get("created_at", 0) >= cutoff]
        # Remember where the group stands even when nothing recent is kept, so the next check starts there.
        return kept or ([{**recent[-1], "_skip": True}] if recent else [])
    out: list[dict] = []
    after = last
    for _ in range(PAGES_PER_CHECK):
        status, body = api.get(f"/groups/{gid}/messages", after_id=after, limit=100)
        batch = sorted((body or {}).get("messages", []), key=lambda m: m.get("created_at", 0)) if status != 304 else []
        if not batch:
            break
        out += batch
        after = str(batch[-1]["id"])
        if len(batch) < 100:
            break
    return out


def _event_text(m: dict) -> str:
    """A GroupMe calendar event attached to a message, as words."""
    for a in m.get("attachments") or []:
        if a.get("type") == "event":
            return f"[GroupMe event: {a.get('name') or a.get('event_id', '')}]"
    return ""


def _pictures(m: dict) -> list[str]:
    """The addresses of the pictures posted in a message."""
    urls = [str(a.get("url") or "") for a in m.get("attachments") or [] if a.get("type") in ("image", "linked_image")]
    return [u for u in urls if u.startswith(PICTURES)][:PICTURES_PER_MESSAGE]


def record(m: dict, gid: str, group: str) -> dict:
    sent = datetime.fromtimestamp(int(m.get("created_at", 0))).astimezone().isoformat(timespec="minutes")
    text = " ".join(t for t in (m.get("text") or "", _event_text(m)) if t).strip()
    pictures = _pictures(m)
    return {
        "source": "groupme",
        "external_id": str(m["id"]),
        "sender": m.get("name") or "someone",
        "address": "",
        "subject": "",
        "channel": group,
        "sent_at": sent,
        "text": text[:1500],
        "pictures": json.dumps(pictures) if pictures else None,
        "link": f"https://web.groupme.com/chats/{gid}",
        "noise": "already seen" if m.get("_skip") else (None if text or pictures else "no text"),
    }
