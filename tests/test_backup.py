import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import backup, config as cfgmod, db, today
from oso.config import Config, Course

TZ = ZoneInfo("America/New_York")
NIGHT = datetime(2026, 11, 2, 2, 15, tzinfo=TZ)


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    nas = tmp_path / "nas" / "oso_backup"
    nas.mkdir(parents=True)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")], backup_folder=str(nas))
    notes = cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes"
    notes.mkdir(parents=True)
    (notes / "Day 1.md").write_text("first")
    (notes / "Day 2.md").write_text("second")
    cfgmod.save(cfg)
    return cfg, nas


def test_nightly_copy_changed_files_and_records(env):
    cfg, nas = env
    with db.connect() as conn:
        conn.execute("CREATE TABLE marks (x)")
        conn.execute("INSERT INTO marks VALUES (42)")
        conn.commit()
        assert backup.due(conn, cfg, NIGHT)
        r = backup.run(cfg, conn, NIGHT)
        assert r["copied"] == 2 and r["finished"] == 1
        assert (nas / "Vault/Courses/2026 Fall/Physics/Notes/Day 1.md").read_text() == "first"
        copy = sqlite3.connect(nas / "Oso" / "oso.sqlite")  # closed below
        assert copy.execute("SELECT x FROM marks").fetchone() == (42,)
        copy.close()
        assert (nas / "Oso/history/oso-2026-11-02.sqlite").exists() and (nas / "Oso/config.toml").exists()
        assert not backup.due(conn, cfg, NIGHT + timedelta(hours=5))  # once a day
        # the next night only the changed file is copied
        time.sleep(1.1)
        (cfg.vault / "Courses/2026 Fall/Physics/Notes/Day 2.md").write_text("second, edited")
        assert backup.run(cfg, conn, NIGHT + timedelta(days=1))["copied"] == 1


def test_deleted_files_kept_then_cleared(env):
    cfg, nas = env
    with db.connect() as conn:
        backup.run(cfg, conn, NIGHT)
        (cfg.vault / "Courses/2026 Fall/Physics/Notes/Day 1.md").unlink()
        r = backup.run(cfg, conn, NIGHT + timedelta(days=1))
        assert r["removed"] == 1
        kept = nas / "Removed/2026-11-03/Courses/2026 Fall/Physics/Notes/Day 1.md"
        assert kept.read_text() == "first" and not (nas / "Vault/Courses/2026 Fall/Physics/Notes/Day 1.md").exists()
        backup.run(cfg, conn, NIGHT + timedelta(days=40))
        assert not (nas / "Removed/2026-11-03").exists()
        assert sorted(p.name for p in (nas / "Oso/history").iterdir()) == ["oso-2026-12-12.sqlite"]


def test_unreachable_folder_is_quiet_then_flagged(env, tmp_path):
    cfg, nas = env
    cfg.backup_folder = str(tmp_path / "unplugged")
    with db.connect() as conn:
        r = backup.run(cfg, conn, NIGHT)
        assert "can't reach" in r["skipped"]
        assert backup.stale_line(conn, cfg, NIGHT) is None  # not after one night
        assert "hasn't been able to make a backup" in backup.stale_line(conn, cfg, NIGHT + timedelta(days=1))
        cfg.backup_folder = str(nas)
        backup.run(cfg, conn, NIGHT)
        assert backup.stale_line(conn, cfg, NIGHT + timedelta(days=2)) is None
        line = backup.stale_line(conn, cfg, NIGHT + timedelta(days=4))
        assert line and "haven't been backed up since" in line
        assert "## Backup" in today.render(conn, cfg, NIGHT + timedelta(days=4))


def test_a_big_first_backup_continues(env):
    cfg, nas = env
    with db.connect() as conn:
        r = backup.run(cfg, conn, NIGHT, budget=-1)
        assert r["finished"] == 0 and backup.last_success(conn) is None
        assert backup.due(conn, cfg, NIGHT + timedelta(minutes=15))
        assert backup.run(cfg, conn, NIGHT + timedelta(minutes=15))["finished"] == 1


def test_no_folder_no_backup_and_no_nagging(env):
    cfg, _ = env
    cfg.backup_folder = None
    with db.connect() as conn:
        assert backup.run(cfg, conn, NIGHT) == {"skipped": "no backup folder set"}
        assert backup.stale_line(conn, cfg, NIGHT + timedelta(days=30)) is None


def test_restore_into_a_fresh_install(env, tmp_path):
    cfg, nas = env
    with db.connect() as conn:
        conn.execute("CREATE TABLE marks (x)")
        conn.execute("INSERT INTO marks VALUES (7)")
        conn.commit()
        backup.run(cfg, conn, NIGHT)
    new = Config(vault=tmp_path / "newvault")
    new.vault.mkdir()
    db.db_path().unlink()
    with pytest.raises(backup.BackupError, match="doesn't hold an Oso backup"):
        backup.restore(new, tmp_path)
    lines = backup.restore(new, nas)
    assert "Restored 2 files" in lines[0]
    assert (new.vault / "Courses/2026 Fall/Physics/Notes/Day 2.md").read_text() == "second"
    check = sqlite3.connect(db.db_path())
    assert check.execute("SELECT x FROM marks").fetchone() == (7,)
    check.close()  # Windows won't replace a file that is open
    restored = cfgmod.load(cfgmod.config_path())
    assert restored.vault == new.vault and [c.code for c in restored.courses] == ["PHYS-110"]
    with pytest.raises(backup.BackupError, match="already has notes"):
        backup.restore(new, nas)
    assert backup.restore(new, nas, overwrite=True)


def test_check_folder(env, tmp_path):
    with pytest.raises(backup.BackupError, match="can't reach"):
        backup.check_folder(tmp_path / "nope")
    backup.check_folder(tmp_path)
