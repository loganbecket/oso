"""Feedback about Oso from the student: bugs and ideas, emailed to whoever builds Oso.

Each goes out from the Gmail account he connected for school email (`mail.py`), so it needs that account signed
in with permission to send. The email has his words as he said them, a one-line summary, the kind (bug or idea),
what he was doing, the Oso version, and the date. Nothing is kept on his computer.
"""

from __future__ import annotations

from datetime import datetime

from .config import Config

TO = "logan@loganbecket.com"
KINDS = ("bug", "idea")


class NotSent(Exception):
    """Feedback that couldn't go out, with a sentence he can read."""


def send(cfg: Config, words: str, kind: str, summary: str, doing: str | None = None, now: datetime | None = None,
         session=None) -> str:
    """Email the feedback. Returns the address it went to."""
    from . import mail, version_label

    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be bug or idea, not {kind!r}")
    if not (words or "").strip() or not (summary or "").strip():
        raise ValueError("feedback needs his words and a one-line summary")
    if session is None:
        if not mail.connected():
            raise NotSent("Feedback goes out by email, and Oso isn't connected to your Gmail. Connect email in the Oso window, then try again.")
        if not mail.can_send():
            raise NotSent("Feedback goes out by email, and Oso needs you to sign in to Gmail once more to send it. "
                          "Click Connect email in the Oso window, then try again.")
    now = now or datetime.now(cfg.tz)
    quoted = "\n".join(f"> {line}" if line else ">" for line in words.strip().splitlines())
    body = (f"{summary.strip()}\n\nKind: {kind}\nOso: {version_label(cfg.installed_version)}\n"
            f"Sent: {now.strftime('%a %b %d %Y, %I:%M %p')}\n\nIn his words:\n\n{quoted}\n")
    if doing and doing.strip():
        body += f"\nWhat he was doing: {doing.strip()}\n"
    try:
        mail.send(TO, f"Oso {kind}: {summary.strip()}", body, session=session)
    except Exception as e:  # noqa: BLE001
        raise NotSent(f"Oso couldn't email your feedback ({e}). Try again in a few minutes.") from e
    return TO
