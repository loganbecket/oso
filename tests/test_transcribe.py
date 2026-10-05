import os
import stat
from pathlib import Path

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
    from test_phase2 import inked_pdf

    cfg = make_cfg(tmp_path)
    cfg.render_height_px = 600
    hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
    inked_pdf(hw / "Notes.pdf")
    with db.connect(tmp_path / "t.sqlite") as conn:
        handwriting.queue_new(conn, cfg)
    png = next((hw / "pages" / "Notes").glob("*.png"))
    with Image.open(png) as im:
        assert abs(im.height - 600) <= 2


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
