"""Canvas calendar feed (.ics). Every Canvas student account has one and schools cannot disable it.

Find it in Canvas under Calendar, then "Calendar Feed". The URL contains a private token,
so it is stored in the credential store, not in config.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar

from ..db import Item

NAME = "canvas_feed"

_COURSE_IN_SUMMARY = re.compile(r"\s*\[([^\[\]]+)\]\s*$")
_EXAM_WORDS = re.compile(r"\b(exam|midterm|final|test)\b", re.IGNORECASE)
_QUIZ_WORDS = re.compile(r"\bquiz\b", re.IGNORECASE)
_READING_WORDS = re.compile(r"\b(read|reading|chapter)\b", re.IGNORECASE)


class CanvasFeed:
    name = NAME

    def __init__(self, url: str, tz: ZoneInfo, timeout: float = 30.0):
        self.url = url
        self.tz = tz
        self.timeout = timeout

    def fetch(self) -> list[Item]:
        resp = requests.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        return parse_ics(resp.content, self.tz)


def parse_ics(data: bytes | str, tz: ZoneInfo) -> list[Item]:
    cal = Calendar.from_ical(data)
    items: list[Item] = []
    for ev in cal.walk("VEVENT"):
        uid = str(ev.get("UID", "")).strip()
        summary = str(ev.get("SUMMARY", "")).strip()
        if not uid or not summary:
            continue
        title, course = split_course(summary)
        due_at, all_day = _when(ev, tz)
        url = ev.get("URL")
        desc = ev.get("DESCRIPTION")
        items.append(
            Item(
                source=NAME,
                external_id=uid,
                kind=classify(uid, title),
                title=title,
                due_at=due_at,
                all_day=all_day,
                course_code=course,
                url=str(url) if url else None,
                description=str(desc).strip() if desc else None,
            )
        )
    return items


def split_course(summary: str) -> tuple[str, str | None]:
    """Canvas appends the course code in brackets: 'Homework 3 [MATH-101-001]'."""
    m = _COURSE_IN_SUMMARY.search(summary)
    if not m:
        return summary, None
    return summary[: m.start()].strip(), m.group(1).strip()


def classify(uid: str, title: str) -> str:
    low_uid = uid.lower()
    if _EXAM_WORDS.search(title):
        return "exam"
    if _QUIZ_WORDS.search(title) or "quiz" in low_uid:
        return "quiz"
    if "assignment" in low_uid:
        return "assignment"
    if _READING_WORDS.search(title):
        return "reading"
    return "event"


def _when(ev, tz: ZoneInfo) -> tuple[datetime | None, bool]:
    """Due time for an event. Assignments carry DTSTART == DTEND == due time; all-day items are dates."""
    raw = ev.get("DTEND") or ev.get("DTSTART")
    if raw is None:
        return None, False
    value = raw.dt
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    if isinstance(value, date):
        # An all-day DTEND is exclusive; Canvas uses DTSTART for the due date.
        start = ev.get("DTSTART")
        day = start.dt if start is not None and isinstance(start.dt, date) and not isinstance(start.dt, datetime) else value
        return datetime.combine(day, time(23, 59), tzinfo=tz), True
    return None, False
