from pathlib import Path

import pytest

from oso import config as cfgmod
from oso import db, fresh, search
from oso.config import Config, Course


def test_fresh_start_keeps_settings_and_obsidian(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    saved = {}
    monkeypatch.setattr(cfgmod, "save", lambda c, path=None: saved.update(cfg=c))

    vault = tmp_path / "home" / "Drive" / "Vault"
    (vault / ".obsidian" / "plugins").mkdir(parents=True)
    (vault / ".obsidian" / "app.json").write_text("{}")
    (vault / "Courses" / "Physics" / "Notes").mkdir(parents=True)
    (vault / "Courses" / "Physics" / "Notes" / "a.md").write_text("x")
    (vault / "Today.md").write_text("x")
    (vault / "stray.md").write_text("x")
    with db.connect() as conn:
        db.upsert_course(conn, "PHYS-110", "Physics", "Physics")
    (data / "search.sqlite").write_text("x")
    (data / "skills" / "base").mkdir(parents=True)
    (data / "models").mkdir()

    cfg = Config(vault=vault, timezone="America/Chicago", courses=[Course("PHYS-110", "Physics", "Physics")], muted_courses=["PHYS-110"], sync_interval_minutes=30)
    lines = fresh.run(cfg)
    assert any("Deleted 3 items" in l for l in lines)
    assert sorted(p.name for p in vault.iterdir()) == [".obsidian", "Clippings", "Courses", "Oso"]
    assert (vault / ".obsidian" / "app.json").exists()
    assert not any((vault / "Courses").iterdir())
    assert not db.db_path().exists() and not search.index_path().exists() and not (data / "skills").exists()
    assert (data / "models").exists()
    kept = saved["cfg"]
    assert kept.courses == [] and kept.muted_courses == []
    assert kept.timezone == "America/Chicago" and kept.sync_interval_minutes == 30


def test_refuses_anything_that_is_not_a_vault(tmp_path: Path):
    with pytest.raises(fresh.NotAVault):
        fresh.check_vault(Path.home())
    with pytest.raises(fresh.NotAVault):
        fresh.check_vault(Path(Path.home().anchor))
    plain = tmp_path / "a" / "b" / "Documents"
    plain.mkdir(parents=True)
    (plain / "taxes.pdf").write_text("x")
    with pytest.raises(fresh.NotAVault):
        fresh.check_vault(plain)
    with pytest.raises(fresh.NotAVault):
        fresh.check_vault(tmp_path / "missing")
