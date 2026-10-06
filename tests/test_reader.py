import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from oso import books, config as cfgmod, convert, merge, ocr, reader, today, transcribe
from oso.config import Config, Course
from oso.db import SCHEMA, Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)
GOOD = "Velocity is the rate of change of position with respect to time and acceleration is the rate of change of velocity " * 2


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics"), Course("BIO-110", "Biology", "2026 Fall/Biology")])
    for c in cfg.courses:
        (cfg.vault / "Courses" / c.folder / "Books").mkdir(parents=True)
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path / "data")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(reader, "_claude", lambda: "claude")
    monkeypatch.setattr(transcribe, "run", lambda conn, cfg, limit=200, model=None: {"pages": 0, "notes": 0, "low_confidence": 0, "failed": 0})
    calls = []

    def fake_read(exe, cfg, image, page, what, course):
        calls.append((course, what, page))
        return f"$E = mc^2$ read from {Path(image).name}"

    monkeypatch.setattr(reader, "read_page", fake_read)
    yield conn, cfg, calls
    conn.close()


def scanned_book(cfg, course_folder, title, texts, monkeypatch):
    scans = cfg.vault / "Courses" / course_folder / "Books" / title / "Scans"
    scans.mkdir(parents=True)
    for i, _ in enumerate(texts):
        Image.new("RGB", (60, 80), "white").save(scans / f"{i:02d}.png")
    monkeypatch.setattr(ocr, "read_images", lambda ps: [texts[int(p.stem[1:]) - 1] for p in ps])
    books.process(cfg)


def test_poor_book_pages_read_automatically_nearest_exam_first(env, monkeypatch):
    conn, cfg, calls = env
    scanned_book(cfg, "2026 Fall/Biology", "Cells", [GOOD, "x+y=2 ∫"], monkeypatch)
    scanned_book(cfg, "2026 Fall/Physics", "Mechanics", ["F=ma Σ", GOOD], monkeypatch)
    merge.apply(conn, [Item(source="s", external_id="e", course_code="PHYS-110", title="Exam 2", kind="exam", due_at=NOW + timedelta(days=3))], "s", NOW)
    assert [(j["course"], j["page"]) for j in reader.waiting(cfg, conn, NOW)] == [("PHYS-110", "1"), ("BIO-110", "2")]
    counts = reader.run(cfg, conn, NOW)
    assert counts == {"read": 2, "failed": 0, "waiting": 0}
    assert [c[0] for c in calls] == ["Physics", "Biology"]
    chapter = next((cfg.vault / "Courses/2026 Fall/Physics/Books/Mechanics").glob("01 *.md")).read_text(encoding="utf-8")
    assert "$E = mc^2$ read from p0001.png" in chapter and "Claude is reading it" not in chapter


def test_optional_daily_limit_and_switch(env, monkeypatch):
    conn, cfg, calls = env
    scanned_book(cfg, "2026 Fall/Physics", "Mechanics", ["Σ1", "Σ2", "Σ3"], monkeypatch)
    cfg.auto_read_per_day = 2
    assert reader.run(cfg, conn, NOW)["read"] == 2
    assert reader.run(cfg, conn, NOW + timedelta(minutes=15))["read"] == 0  # today's limit is used up
    assert reader.run(cfg, conn, NOW + timedelta(days=1))["read"] == 1      # a new day
    cfg.auto_read = False
    assert reader.run(cfg, conn, NOW + timedelta(days=2)) == {"read": 0, "failed": 0, "waiting": 0}


def test_time_limit_per_check(env, monkeypatch):
    conn, cfg, calls = env
    scanned_book(cfg, "2026 Fall/Physics", "Mechanics", ["Σ1", "Σ2", "Σ3"], monkeypatch)
    clock = iter([0, 10, 100, 200] + [99999] * 10)  # start, handwriting check, then one check per page
    monkeypatch.setattr(reader.time, "monotonic", lambda: next(clock))
    counts = reader.run(cfg, conn, NOW)
    assert counts["read"] == 2 and counts["waiting"] == 1  # stopped starting new pages at the time limit


def test_scanned_handout_pages_read_in_place(env, monkeypatch):
    conn, cfg, calls = env
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "read_images", lambda ps: [GOOD, "∫ f(x) dx = ?"])
    lect = cfg.vault / "Courses/2026 Fall/Physics/Lectures"
    lect.mkdir(parents=True)
    pdf = lect / "Worksheet 3.pdf"
    Image.new("L", (600, 800), 255).save(pdf, save_all=True, append_images=[Image.new("L", (600, 800), 255)])
    convert.convert_vault(cfg)
    md = lect / "Worksheet 3.pdf.md"
    assert "oso:needs-reading" in md.read_text(encoding="utf-8")
    assert "Claude is reading 1 page" in today.render(conn, cfg, NOW)
    assert reader.run(cfg, conn, NOW)["read"] == 1
    text = md.read_text(encoding="utf-8")
    assert "oso:needs-reading" not in text and "$E = mc^2$ read from p002.png" in text and "![[Courses/2026 Fall/Physics/Lectures/pages/Worksheet 3/p002.png]]" in text
    assert "rate of change of position" in text  # the clean page kept its own text
    assert "## Reading" not in today.render(conn, cfg, NOW)


def test_handwriting_first(env, monkeypatch):
    conn, cfg, calls = env
    order = []
    monkeypatch.setattr(reader, "handwriting_waiting", lambda conn: 0 if order else 1)

    def fake_transcribe(conn, cfg, limit=200, model=None):
        order.append("handwriting")
        return {"pages": 1, "notes": 1, "low_confidence": 0, "failed": 0}

    monkeypatch.setattr(transcribe, "run", fake_transcribe)
    scanned_book(cfg, "2026 Fall/Physics", "Mechanics", ["Σ1"], monkeypatch)
    monkeypatch.setattr(reader, "read_page", lambda *a: order.append("book") or "text")
    assert reader.run(cfg, conn, NOW)["read"] == 2
    assert order == ["handwriting", "book"]
