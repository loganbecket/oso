import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import db, update
from oso.config import Config

TZ = ZoneInfo("America/New_York")


def git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def make_repos(tmp_path: Path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "master")
    git(origin, "config", "user.email", "t@t")
    git(origin, "config", "user.name", "t")
    (origin / "a.txt").write_text("1")
    git(origin, "add", "a.txt")
    git(origin, "commit", "-q", "-m", "one")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
    return origin, clone


def test_status_and_daily_check(tmp_path: Path, monkeypatch):
    origin, clone = make_repos(tmp_path)
    cfg = Config(vault=tmp_path / "vault")
    monkeypatch.setattr(update.cfgmod, "save", lambda c, path=None: None)
    update.set_repo(cfg, clone)
    assert update.status(cfg)["available"] is False

    (origin / "a.txt").write_text("2")
    git(origin, "commit", "-q", "-am", "two")
    st = update.status(cfg)
    assert st["available"] and st["behind"] == 1 and "oso update" in st["message"]

    now = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)
    with db.connect(tmp_path / "t.sqlite") as conn:
        assert "update is available" in update.check_daily(conn, cfg, now)
        # Within a day the cached message is reused without fetching.
        monkeypatch.setattr(update, "status", lambda *a, **k: (_ for _ in ()).throw(AssertionError("fetched")))
        assert "update is available" in update.check_daily(conn, cfg, now)


def test_unknown_repo_is_a_plain_message(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault")
    st = update.status(cfg)
    assert not st["known"] and "oso set-repo" in st["message"]
    assert "oso set-repo" in update.run(cfg)
