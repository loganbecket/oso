from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import dashboard, db, drive, merge, today
from oso.config import Config, Course
from oso.db import Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


def test_dashboard_renders(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("MATH-101-001", "Calculus I", "Calculus I")])
    cfg.vault.mkdir()
    with db.connect(tmp_path / "t.sqlite") as conn:
        merge.apply(
            conn,
            [
                Item(source="syllabus", external_id="h1", kind="assignment", title="HW 1", due_at=NOW + timedelta(days=1), course_code="MATH-101-001", weight=30),
                Item(source="syllabus", external_id="e1", kind="exam", title="Midterm", due_at=NOW + timedelta(days=9), course_code="MATH-101-001", weight=40),
            ],
            "syllabus",
            NOW,
        )
        conn.execute("UPDATE items SET grade_points = 8, grade_max = 10 WHERE external_id = 'h1'")
        run = db.record_sync(conn, "canvas_feed")
        db.finish_sync(conn, run, ok=True)
        path = dashboard.write(conn, cfg, NOW)
    text = path.read_text()
    assert "| [[Courses/Calculus I/Course\\|Calculus I]] | 80.0% |" in text
    assert "Week of Oct 05" in text and "1 exam" in text
    assert "canvas_feed: last success" in text and ", ok" in text


def test_today_nudges_unstarted_items(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("MATH-101-001", "Calculus I", "Calculus I")])
    with db.connect(tmp_path / "t.sqlite") as conn:
        merge.apply(conn, [Item(source="canvas_feed", external_id="a", kind="assignment", title="HW 9", due_at=NOW + timedelta(hours=10), course_code="MATH-101-001")], "canvas_feed", NOW)
        text = today.render(conn, cfg, NOW)
        assert "## Not started yet" in text and "HW 9 is due within a day" in text
        conn.execute("UPDATE items SET user_status = 'started'")
        assert "## Not started yet" not in today.render(conn, cfg, NOW)


def test_drive_mirror_copies_new_files_only(tmp_path: Path):
    src = tmp_path / "drive" / "Physics"
    src.mkdir(parents=True)
    (src / "Lecture 1.pdf").write_bytes(b"%PDF-1.4 fake")
    (src / "Doc.gdoc").write_text("{}")
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics", drive_folder=str(src))])
    assert drive.mirror(cfg) == 2
    assert (cfg.vault / "Courses" / "Physics" / "Drive" / "Lecture 1.pdf").exists()
    assert (cfg.vault / "Courses" / "Physics" / "Drive" / "Doc.gdoc").exists()
    assert drive.mirror(cfg) == 0


def test_filing_moves_clips_with_a_course(tmp_path: Path):
    from oso import filing

    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    inbox = cfg.vault / "Inbox"
    inbox.mkdir(parents=True)
    (inbox / "Orbital mechanics.md").write_text("---\ntype: reading\ncourse: physics\nsource: https://x\n---\n\nbody\n")
    (inbox / "Unfiled.md").write_text("---\ntype: reading\ncourse: \n---\n\nbody\n")
    assert filing.file_inbox(cfg) == 1
    moved = cfg.vault / "Courses" / "Physics" / "Readings" / "Orbital mechanics.md"
    assert moved.exists() and "course: PHYS-110" in moved.read_text()
    assert (inbox / "Unfiled.md").exists()


def test_vault_instructions_written_and_switchable(tmp_path: Path):
    from oso import instructions

    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    cfg.vault.mkdir()
    path = instructions.write(cfg)
    text = path.read_text()
    assert "**Physics** (`PHYS-110`)" in text and "oso-quiz" in text
    cfg.write_vault_instructions = False
    assert instructions.write(cfg) is None


def test_read_note_cap_and_section(tmp_path: Path, monkeypatch):
    from oso import mcp_server

    cfg = Config(vault=tmp_path / "vault", read_cap_chars=50)
    cfg.vault.mkdir()
    (cfg.vault / "big.md").write_text("---\ntype: lecture\n---\n# Intro\n\n" + "a" * 100 + "\n\n## Chain rule\n\nThe chain rule text.\n")
    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    first = mcp_server.read_note("big.md")
    assert first["truncated"] and len(first["text"]) == 50 and first["next_start"] == 50
    rest = mcp_server.read_note("big.md", start=first["next_start"])
    assert rest["truncated"] and rest["next_start"] == 100
    whole = mcp_server.read_note("big.md", max_chars=0)
    assert not whole["truncated"] and "Chain rule" in whole["text"]
    cfg.read_cap_chars = 0
    assert not mcp_server.read_note("big.md")["truncated"]
    sec = mcp_server.read_section("big.md", "Chain rule")
    assert sec["found"] and sec["text"] == "The chain rule text."
    assert not mcp_server.read_section("big.md", "Nope")["found"]
    try:
        mcp_server.read_note("../outside.md")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
