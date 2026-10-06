from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import config as cfgmod
from oso import courses, db, search, today
from oso.config import Config
from oso.db import Item


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    saved = {}
    monkeypatch.setattr(cfgmod, "save", lambda c, path=None: saved.update(cfg=c))
    real = db.connect
    monkeypatch.setattr(db, "connect", lambda *a, **k: real(tmp_path / "t.sqlite"))
    return Config(vault=tmp_path / "vault")


def test_terms():
    assert courses.term_for(date(2026, 9, 1)) == "2026 Fall"
    assert courses.term_for(date(2027, 2, 1)) == "2027 Spring"
    assert courses.check_term("2026 fall") == "2026 Fall"
    with pytest.raises(ValueError):
        courses.check_term("Fall semester")


def test_register_under_term_relate_and_finish(env):
    calc2 = courses.register(env, "MATH-1302", "Calculus II", term="2026 Fall")
    assert calc2.folder == "2026 Fall/Calculus II"
    assert (env.vault / "Courses" / "2026 Fall" / "Calculus II" / "Handwriting").is_dir()
    calc3 = courses.register(env, "MATH-2301", "Calculus III", term="2027 Spring", related=["Calculus II"])
    assert calc3.related == ["MATH-1302"]
    again = courses.register(env, "MATH-1302", "Calculus 2", term="2027 Spring")
    assert again.folder == "2026 Fall/Calculus II"  # never moves
    with pytest.raises(ValueError):
        courses.register(env, "X", "X", related=["Nope"])

    courses.update(env, "MATH-1302", finished=True)
    assert not env.is_active("MATH-1302") and env.is_active("MATH-2301") and env.is_active(None)
    assert search.scope(env, None) is None
    assert search.scope(env, "MATH-2301") == {"math-2301", "math-1302"}
    assert search.scope(env, "Calculus 2") == {"math-1302"}


def test_finished_courses_leave_today_and_default_search(env, tmp_path: Path, monkeypatch):
    courses.register(env, "ENGL-1301", "Composition", term="2026 Fall")
    courses.register(env, "MATH-1302", "Calculus II", term="2026 Fall")
    tz = ZoneInfo("America/New_York")
    now = datetime(2027, 1, 20, 9, 0, tzinfo=tz)
    with db.connect() as conn:
        from oso import merge

        merge.apply(conn, [Item(source="syllabus", external_id="e1", course_code="ENGL-1301", title="Essay", kind="assignment", due_at=now + timedelta(days=2))], "syllabus", now)
        merge.apply(conn, [Item(source="syllabus2", external_id="m1", course_code="MATH-1302", title="Old quiz", kind="quiz", due_at=now - timedelta(days=30))], "syllabus2", now)
        text = today.render(conn, env, now)
        assert "Essay" in text and "Calculus II has had nothing due for two weeks" in text
        courses.update(env, "ENGL-1301", finished=True)
        courses.update(env, "MATH-1302", finished=True)
        text = today.render(conn, env, now)
        assert "Essay" not in text and "nothing due for two weeks" not in text

    for folder, word in (("2026 Fall/Composition", "thesis"), ("2026 Fall/Calculus II", "series")):
        (env.vault / "Courses" / folder / "Notes" / "n.md").write_text(f"# {word}\n\nAbout the {word}.\n")
    monkeypatch.setattr(search, "embed_passages", lambda texts: None)
    monkeypatch.setattr(search, "embed_query", lambda text: None)
    idx = tmp_path / "s.sqlite"
    search.update(env, idx)
    assert search.query(env, "thesis", path=idx) == []
    assert search.query(env, "thesis", course="Composition", path=idx)[0]["course"] == "ENGL-1301"


def test_converted_copies_know_their_nested_course(env):
    from oso import convert

    courses.register(env, "MATH-1302", "Calculus II", term="2026 Fall")
    courses.register(env, "MATH-1302B", "Calculus", term="2026 Fall")
    f = env.vault / "Courses" / "2026 Fall" / "Calculus II" / "Lectures" / "x.pdf"
    assert convert._course_from_path(env, f) == "MATH-1302"
    assert convert._course_from_path(env, env.vault / "Courses" / "2026 Fall" / "Calculus" / "x.pdf") == "MATH-1302B"
