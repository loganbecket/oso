import os
import stat
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from oso import db, handwriting, transcribe
from oso.config import Config, Course


def make_cfg(tmp_path: Path) -> Config:
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    (cfg.vault / "Courses" / "Physics" / "Handwriting").mkdir(parents=True)
    return cfg


def test_blank_pages_are_skipped(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    Image.new("L", (800, 1000), 255).save(hw / "empty.png")
    img = Image.new("L", (800, 1000), 255)
    ImageDraw.Draw(img).text((100, 100), "F = ma\n" * 20, fill=0)
    ImageDraw.Draw(img).rectangle((100, 400, 600, 420), fill=0)
    img.save(hw / "written.png")
    with db.connect(tmp_path / "t.sqlite") as conn:
        assert handwriting.queue_new(conn, cfg) == 1
        pend = handwriting.pending(conn)
        assert [p["notebook"] for p in pend] == ["written"]
        assert conn.execute("SELECT status FROM pages WHERE notebook = 'empty'").fetchone()["status"] == "blank"


def test_render_height_setting(tmp_path: Path):
    from test_notes_and_convert import inked_pdf

    cfg = make_cfg(tmp_path)
    cfg.render_height_px = 600
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    inked_pdf(hw / "Notes.pdf")
    with db.connect(tmp_path / "t.sqlite") as conn:
        handwriting.queue_new(conn, cfg)
    png = next((hw / "pages" / "Notes").glob("*.png"))
    with Image.open(png) as im:
        assert abs(im.height - 600) <= 2


@pytest.mark.skipif(sys.platform == "win32", reason="the fake claude is a bash script")
def test_transcribe_one_page_per_call(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    for n in (1, 2):
        img = Image.new("L", (800, 1000), 255)
        ImageDraw.Draw(img).rectangle((100, 100, 700, 300), fill=0)
        img.save(hw / f"page{n}.png")

    fake = tmp_path / "bin" / "claude"
    fake.parent.mkdir()
    log = tmp_path / "calls.log"
    fake.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log}"
echo "# Newton"
echo ""
echo "\\$F = ma\\$"
echo "CONFIDENCE: 0.9"
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")

    with db.connect(tmp_path / "t.sqlite") as conn:
        handwriting.queue_new(conn, cfg)
        counts = transcribe.run(conn, cfg)
        assert counts["pages"] == 2 and counts["notes"] == 2 and counts["failed"] == 0
        assert handwriting.pending(conn) == []
    calls = log.read_text()
    assert calls.count("--model sonnet") == 2
    note = next((cfg.vault / "Courses" / "Physics" / "Notes").glob("*page1.md"))
    text = note.read_text()
    assert "course: PHYS-110" in text and "confidence: 0.9" in text
    assert "$F = ma$" in text and "![[Courses/Physics/Handwriting/page1.png]]" in text


def test_transcribe_without_claude_is_a_plain_error(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    with db.connect(tmp_path / "t.sqlite") as conn:
        try:
            transcribe.run(conn, cfg)
            raise AssertionError("expected ClaudeMissing")
        except transcribe.ClaudeMissing as e:
            assert "claude.ai/code" in str(e)


def test_his_notes_are_never_overwritten_and_pages_stay_queued(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    img = Image.new("L", (800, 1000), 255)
    ImageDraw.Draw(img).rectangle((100, 100, 700, 300), fill=0)
    img.save(hw / "page1.png")
    monkeypatch.setattr(transcribe.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(transcribe, "_transcribe_page", lambda exe, cfg, model, p, course: ("$F = ma$", 0.9))
    notes_dir = cfg.vault / "Courses" / "Physics" / "Notes"
    notes_dir.mkdir()
    with db.connect(tmp_path / "t.sqlite") as conn:
        handwriting.queue_new(conn, cfg)
        day = transcribe._note_path(cfg, "PHYS-110", "page1", handwriting.pending(conn)[0]["queued_at"])
        day.write_text("# Mine\n\nmy own notes\n", encoding="utf-8")
        cont = day.with_name(f"{day.stem} (continued).md")
        cont.write_text("# Also mine\n", encoding="utf-8")
        # Both the dated note and "(continued)" are his: the page goes to "(continued 2)".
        counts = transcribe.run(conn, cfg)
        assert counts["pages"] == 1 and counts["failed"] == 0
        assert day.read_text(encoding="utf-8") == "# Mine\n\nmy own notes\n" and cont.read_text(encoding="utf-8") == "# Also mine\n"
        cont2 = day.with_name(f"{day.stem} (continued 2).md")
        assert "$F = ma$" in cont2.read_text(encoding="utf-8") and handwriting.pending(conn) == []
        # A write that is refused (the note became his between the check and the write) leaves the page queued.
        img.save(hw / "page2.png")
        handwriting.queue_new(conn, cfg)
        monkeypatch.setattr(transcribe.vault, "write_note", lambda *a, **k: False)
        counts = transcribe.run(conn, cfg)
        assert counts["pages"] == 0 and counts["failed"] == 1
        assert [p["notebook"] for p in handwriting.pending(conn)] == ["page2"]


def test_a_damaged_scan_is_skipped_and_the_rest_still_queued(tmp_path: Path, monkeypatch):
    cfg = make_cfg(tmp_path)
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    (hw / "a.jpg").write_bytes(b"not a picture at all")  # sorts before the good one
    img = Image.new("L", (800, 1000), 255)
    ImageDraw.Draw(img).rectangle((100, 100, 700, 300), fill=0)
    img.save(hw / "b.png")
    with db.connect(tmp_path / "t.sqlite") as conn:
        assert handwriting.queue_new(conn, cfg) == 1
        assert [p["notebook"] for p in handwriting.pending(conn)] == ["b"]
        assert conn.execute("SELECT status FROM pages WHERE path = 'Courses/Physics/Handwriting/a.jpg'").fetchone()["status"] == "unreadable"
        looked = []
        real = handwriting.is_blank
        monkeypatch.setattr(handwriting, "is_blank", lambda p, **k: looked.append(p.name) or real(p, **k))
        assert handwriting.queue_new(conn, cfg) == 0
        assert looked == []  # neither the damaged scan nor the already queued one is opened again
