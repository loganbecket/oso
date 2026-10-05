from datetime import datetime
from zoneinfo import ZoneInfo

from oso.connectors.canvas_feed import classify, parse_ics, split_course

TZ = ZoneInfo("America/New_York")

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Instructure//Canvas//EN
BEGIN:VEVENT
UID:event-assignment-123
SUMMARY:Homework 3 [MATH-101-001]
DTSTART:20261012T035900Z
DTEND:20261012T035900Z
URL:https://school.instructure.com/courses/1/assignments/123
DESCRIPTION:Sections 2.1 to 2.4
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-124
SUMMARY:Midterm 1 [PHYS-110-002]
DTSTART;VALUE=DATE:20261020
DTEND;VALUE=DATE:20261021
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-9
SUMMARY:Lab safety orientation
DTSTART:20261001T140000Z
DTEND:20261001T150000Z
END:VEVENT
END:VCALENDAR
"""


def test_parse_assignment_with_time():
    items = parse_ics(ICS, TZ)
    hw = next(i for i in items if i.external_id == "event-assignment-123")
    assert hw.title == "Homework 3"
    assert hw.course_code == "MATH-101-001"
    assert hw.kind == "assignment"
    assert hw.due_at == datetime(2026, 10, 11, 23, 59, tzinfo=TZ)
    assert not hw.all_day
    assert hw.url.endswith("/assignments/123")
    assert hw.description == "Sections 2.1 to 2.4"


def test_all_day_exam_uses_start_date():
    items = parse_ics(ICS, TZ)
    exam = next(i for i in items if i.external_id == "event-assignment-124")
    assert exam.kind == "exam"
    assert exam.all_day
    assert exam.due_at.date().isoformat() == "2026-10-20"


def test_event_without_course():
    items = parse_ics(ICS, TZ)
    ev = next(i for i in items if i.external_id == "event-calendar-event-9")
    assert ev.course_code is None
    assert ev.kind == "event"


def test_split_course():
    assert split_course("Quiz 2 [CHEM-100]") == ("Quiz 2", "CHEM-100")
    assert split_course("No brackets here") == ("No brackets here", None)


def test_classify():
    assert classify("event-assignment-1", "Final Exam") == "exam"
    assert classify("event-assignment-1", "Quiz 4") == "quiz"
    assert classify("event-assignment-1", "Problem Set 2") == "assignment"
    assert classify("event-calendar-event-1", "Read chapter 3") == "reading"
