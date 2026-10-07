"""Filing clips with no course typed: by book, by the syllabus that names a book, by content, never a syllabus,
and moving clips and books at his word."""

import re
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from oso import filing, search, today
from oso.config import Config, Course
from oso.db import SCHEMA

VOCAB = ["force", "torque", "velocity", "acceleration", "newton", "charge", "voltage", "current", "resistor", "circuit",
         "integral", "series", "derivative", "converge", "civil", "war", "constitution", "amendment", "president", "oven"]


def fake_embed(texts):
    out = []
    for t in texts:
        words = re.findall(r"[a-z]+", t.lower())
        v = np.array([sum(w.startswith(k) for w in words) for k in VOCAB], dtype=np.float32) + 0.05
        out.append((v / np.linalg.norm(v)).tobytes())
    return out


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    cfg = Config(vault=tmp_path / "vault", courses=[
        Course("PHYS-110", "Physics 1", "2026 Fall/Physics 1"), Course("PHYS-120", "Physics 2", "2026 Fall/Physics 2"),
        Course("HIST-101", "US History", "2026 Fall/US History"), Course("OLD-100", "Old course", "2025 Fall/Old", finished=True)])
    for c in cfg.courses:
        (cfg.vault / "Courses" / c.folder).mkdir(parents=True)
    (cfg.vault / "Clippings").mkdir()
    material = {"PHYS-110": "force torque newton acceleration velocity force torque",
                "PHYS-120": "charge voltage current resistor circuit charge",
                "HIST-101": "civil war constitution amendment president civil",
                "OLD-100": "oven oven oven"}
    profiles = {code: [np.frombuffer(fake_embed([text])[0], dtype=np.float32)] * 3 for code, text in material.items() if code != "OLD-100"}
    monkeypatch.setattr(filing, "course_profiles", lambda cfg: profiles)
    monkeypatch.setattr(search, "embed_passages", fake_embed)
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    yield cfg, conn
    conn.close()


def clip(cfg, name, body, **fm):
    head = "".join(f"{k}: {v}\n" for k, v in {"type": "reading", **fm}.items())
    (cfg.vault / "Clippings" / f"{name}.md").write_text(f"---\n{head}---\n\n{body}\n")


def test_clips_go_to_the_course_they_clearly_match_and_the_rest_wait(env):
    cfg, conn = env
    clip(cfg, "Torque explained", "Torque is force times the lever arm; newton meters; angular acceleration.")
    clip(cfg, "Gettysburg", "The civil war battle; the president spoke; later the amendment.")
    clip(cfg, "Energy", "force charge voltage velocity")  # both physics courses equally: unclear
    clip(cfg, "Cookies", "Preheat the oven.")  # matches nothing (and never a finished course)
    assert filing.file_clippings(cfg, conn) == 2
    assert (cfg.vault / "Courses/2026 Fall/Physics 1/Readings/Torque explained.md").exists()
    assert "course: HIST-101" in (cfg.vault / "Courses/2026 Fall/US History/Readings/Gettysburg.md").read_text()
    assert sorted(filing.unplaced(cfg)) == ["Cookies", "Energy"]
    assert {r["how"] for r in filing.recently_filed(conn, "2000")} == {"content"}


def test_a_syllabus_is_never_filed(env):
    cfg, conn = env
    clip(cfg, "PHYS 130 Syllabus", "# Physics 3 syllabus\nforce torque newton. Office hours Tuesday. Grading: exams 50%.", title="PHYS 130 Syllabus")
    clip(cfg, "Course info", "Instructor: Dr. Lee. Office hours: MWF. Grading policy. Late policy: none. force torque newton torque")
    assert filing.file_clippings(cfg, conn) == 0
    assert filing.unplaced(cfg) == []  # waiting for /create-course, not asked about


def test_book_pages_find_their_course_and_follow_each_other(env):
    cfg, conn = env
    (cfg.vault / "Courses/2026 Fall/Physics 2/Syllabus.md").write_text("Required text: Fundamentals of Physics, Halliday, Resnick, Walker.")
    clip(cfg, "p1", "A page about charge.", book="Fundamentals of Physics, Halliday", page="'12'")
    clip(cfg, "p2", "A page about anything.", book="Halliday", page="'13'")
    assert filing.file_clippings(cfg, conn) == 2
    clipped = cfg.vault / "Courses/2026 Fall/Physics 2/Books/Fundamentals of Physics, Halliday/Clipped"
    assert sorted(p.name for p in clipped.iterdir()) == ["p1.md", "p2.md"]  # the partial title joins the same book
    assert "## p. 13" in (clipped / "p2.md").read_text()
    # Wrong course: the whole book moves, and later pages follow it.
    assert "Moved Fundamentals of Physics, Halliday from Physics 2 to Physics 1" in filing.move_book(cfg, "Halliday", "PHYS-110")
    clip(cfg, "p3", "x", book="Halliday", page="'14'")
    filing.file_clippings(cfg, conn)
    assert (cfg.vault / "Courses/2026 Fall/Physics 1/Books/Fundamentals of Physics, Halliday/Clipped/p3.md").exists()
    assert "course: PHYS-110" in (cfg.vault / "Courses/2026 Fall/Physics 1/Books/Fundamentals of Physics, Halliday/Clipped/p1.md").read_text()


def test_moving_clips_at_his_word(env):
    cfg, conn = env
    clip(cfg, "Energy", "force charge voltage velocity")
    clip(cfg, "Cookies", "Preheat the oven.")
    assert filing.file_clip(cfg, "energy", "Physics 2", conn) == "Filed Energy in Physics 2."
    assert "not tied to a course" in filing.file_clip(cfg, "cookies", "none", conn)
    assert filing.unplaced(cfg) == []
    filing.file_clippings(cfg, conn)
    assert (cfg.vault / "Clippings/Cookies.md").exists()  # stays, and isn't asked about again
    assert filing.file_clip(cfg, "energy", "PHYS-110", conn) == "Filed Energy in Physics 1."  # from one course to another
    assert (cfg.vault / "Courses/2026 Fall/Physics 1/Readings/Energy.md").exists()


def test_the_briefing_says_what_was_filed_and_asks_about_the_rest(env):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    cfg, conn = env
    clip(cfg, "Torque explained", "Torque is force times the lever arm; newton.")
    clip(cfg, "Energy", "force charge voltage velocity")
    filing.file_clippings(cfg, conn)
    text = today.render(conn, cfg, datetime.now(ZoneInfo("America/New_York")))
    assert "- Filed 1 clip since yesterday: 1 Physics 1." in text and 'ask him: "Energy".' in text


def test_the_template_has_no_course_box():
    import json

    t = json.loads((Path(__file__).parent.parent / "obsidian" / "web-clipper-template.json").read_text())
    names = [p["name"] for p in t["properties"]]
    assert "course" not in names and "book" in names and "page" in names
