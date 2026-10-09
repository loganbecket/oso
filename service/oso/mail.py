"""School email: on every check, read what arrived in the Gmail account his school email is forwarded to.

Reading uses the `gmail.readonly` permission, on the one account he connects with `oso connect-email`; the
`gmail.send` permission is only for sending his feedback about Oso (`feedback.py`). School
email reaches it through a forwarding rule in the school account; a message forwarded with the original sender
inside it ("From: ... Subject: ...") is unwrapped, so the sender, subject, and text are the original's. Obvious noise is set aside here, with no Claude involved: Gmail's
Promotions and Social tabs, Canvas's own notification emails (Oso reads Canvas directly), and senders or
mailing lists he has muted. What is left is kept as a short record (sender, subject, date, a trimmed copy of the
text, a link back to the message) for Claude to pick the facts out of (`messages.py`); the text is dropped once
that is done. Nothing from a message is copied into the vault.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import quote

from . import messages, secrets
from .config import Config

log = logging.getLogger("oso.mail")

SEND = "https://www.googleapis.com/auth/gmail.send"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", SEND]
API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN = "google_mail_token"
ADDRESS = "google_mail_address"
FIRST_DAYS = 3  # the first check looks back this far
MAX_PER_CHECK = 300
NOISE_LABELS = {"CATEGORY_PROMOTIONS": "promotion", "CATEGORY_SOCIAL": "social network", "SPAM": "spam", "TRASH": "trash"}
CANVAS_SENDERS = ("instructure.com", "canvaslms.com")


def connected() -> bool:
    return bool(secrets.get(TOKEN))


def address() -> str | None:
    return secrets.get(ADDRESS)


def can_send() -> bool:
    """False for an account connected before Oso asked for permission to send; signing in again fixes it."""
    import json

    raw = secrets.get(TOKEN)
    return bool(raw) and SEND in (json.loads(raw).get("scopes") or [])


def send(to: str, subject: str, body: str, session=None) -> None:
    """Send a plain-text email from the connected account."""
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["To"] = to
    if address():
        msg["From"] = address()
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = (session or _session()).post(f"{API}/messages/send", json={"raw": raw})
    r.raise_for_status()


def connect(client_file=None) -> str:
    """The one-time browser sign-in with the school account. Returns the address that was connected."""
    from . import gcal

    creds = gcal.sign_in(SCOPES, client_file)
    secrets.set(TOKEN, creds.to_json())
    r = _session().get(f"{API}/profile")
    r.raise_for_status()
    addr = r.json().get("emailAddress", "")
    secrets.set(ADDRESS, addr)
    return addr


def disconnect() -> None:
    secrets.delete(TOKEN)
    secrets.delete(ADDRESS)


def _session():
    import json

    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    raw = secrets.get(TOKEN)
    if not raw:
        raise messages.NotConnected("school email is not connected")
    creds = Credentials.from_authorized_user_info(json.loads(raw))  # the permissions it was granted, which may be read-only
    if not creds.valid:
        creds.refresh(Request())
        secrets.set(TOKEN, creds.to_json())
    return AuthorizedSession(creds)


def fetch(conn: sqlite3.Connection, cfg: Config, now: datetime, session=None) -> dict[str, int]:
    """Store every message that arrived since the last check. Returns counts of kept and set-aside messages."""
    messages.ensure(conn)
    session = session or _session()
    after = messages.meta_get(conn, "mail_after")
    since = int(after) if after else int((now - timedelta(days=FIRST_DAYS)).timestamp())
    query = f"after:{since} -in:sent -in:drafts -in:chats"
    ids: list[str] = []
    page = None
    while len(ids) < MAX_PER_CHECK:
        params = {"q": query, "maxResults": 100}
        if page:
            params["pageToken"] = page
        r = session.get(f"{API}/messages", params=params)
        r.raise_for_status()
        body = r.json()
        ids += [m["id"] for m in body.get("messages", [])]
        page = body.get("nextPageToken")
        if not page:
            break
    counts = {"kept": 0, "set_aside": 0}
    newest = since
    mailbox = address() or ""
    for mid in ids[:MAX_PER_CHECK]:
        if messages.known(conn, "email", mid):
            continue
        r = session.get(f"{API}/messages/{mid}", params={"format": "full"})
        r.raise_for_status()
        rec = parse(r.json(), mailbox)
        newest = max(newest, int(rec.pop("internal", since)))
        rec["noise"] = noise(rec, cfg)
        messages.store(conn, rec)
        counts["set_aside" if rec["noise"] else "kept"] += 1
    messages.meta_set(conn, "mail_after", str(newest))
    return counts


def parse(msg: dict, mailbox: str = "") -> dict:
    """A Gmail message as Oso keeps it."""
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    name, addr = parseaddr(headers.get("from", ""))
    subject = headers.get("subject", "(no subject)")
    text = body_text(payload)
    original = unwrap_forward(text)
    if original:
        name, addr, subject, text = original["name"] or name, original["address"] or addr, original["subject"] or subject, original["text"]
    try:
        sent = parsedate_to_datetime(headers["date"]).isoformat(timespec="minutes")
    except (KeyError, TypeError, ValueError):
        sent = datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000).astimezone().isoformat(timespec="minutes")
    link = f"https://mail.google.com/mail/?authuser={quote(mailbox)}#all/{msg['id']}" if mailbox else f"https://mail.google.com/mail/#all/{msg['id']}"
    return {
        "source": "email",
        "external_id": msg["id"],
        "sender": name or addr,
        "address": addr.lower(),
        "subject": subject,
        "channel": headers.get("list-id", ""),
        "sent_at": sent,
        "text": trim(text),
        "link": link,
        "labels": msg.get("labelIds", []),
        "internal": int(msg.get("internalDate", 0)) // 1000,
    }


def noise(rec: dict, cfg: Config) -> str | None:
    """Why a message is set aside without Claude reading it, or None when it might matter."""
    for label, why in NOISE_LABELS.items():
        if label in rec.get("labels", []):
            return why
    addr = rec.get("address", "")
    if any(addr.endswith(d) or f"@{d}" in addr or f".{d}" in addr for d in CANVAS_SENDERS):
        return "Canvas notification"
    for muted in cfg.muted_senders:
        m = muted.strip().lower()
        if m and (m == addr or (m.startswith("@") and addr.endswith(m)) or ("@" not in m and addr.endswith("@" + m))
                  or m in (rec.get("channel") or "").lower()):
            return "muted sender"
    return None


def body_text(payload: dict) -> str:
    """The message's plain text, from its text part or, failing that, its HTML part."""
    plain, rich = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(_strip_html(_decode(data)))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return "\n".join(plain) if plain else "\n".join(rich)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


FORWARD_HEADER = re.compile(
    r"^[ \t]*\*?From:\*?[ \t]*(?P<from>.+?)[ \t]*\n(?P<rest>(?:[ \t]*\*?(?:Sent|Date|To|Cc|Subject|Reply-To):\*?.*\n){1,6})",
    re.M,
)


def unwrap_forward(text: str) -> dict | None:
    """The original message inside a forwarded one (Outlook's and Gmail's forward formats), or None when the
    message wasn't forwarded that way. Only a header block near the top counts, so a reply quoted further down
    isn't mistaken for a forward."""
    m = FORWARD_HEADER.search(text)
    if not m or len(text[:m.start()].strip()) > 400:
        return None
    subject = re.search(r"^[ \t]*\*?Subject:\*?[ \t]*(.*)$", m.group("rest"), re.M)
    raw = m.group("from").replace("[mailto:", "<").replace("]", ">")
    angle = re.fullmatch(r'\s*"?(.*?)"?\s*<([^>]+)>\s*', raw)  # "Lee, Dana <dlee@...>": parseaddr trips on the comma
    name, addr = (angle.group(1).strip(), angle.group(2).strip()) if angle else parseaddr(raw)
    return {"name": name, "address": addr.lower(), "subject": subject.group(1).strip() if subject else "", "text": text[m.end():]}


REPLY_START = re.compile(r"^(On .+ wrote:|-----Original Message-----|From: .+)$", re.M)


def trim(text: str, limit: int = 3000) -> str:
    """The new part of a message: quoted replies and signatures' long tails cut, whitespace tidied."""
    m = REPLY_START.search(text)
    if m:
        text = text[:m.start()]
    lines = [ln.rstrip() for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text[:limit]
