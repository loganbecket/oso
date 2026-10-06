from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import db, update
from oso.config import Config

TZ = ZoneInfo("America/New_York")


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, ""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fake_github(tags, sha="abcdef1234567890"):
    def get(url, **kw):
        if url.endswith("/tags"):
            return Resp([{"name": t} for t in tags])
        if url.endswith("/commits/master"):
            return Resp({"sha": sha})
        raise AssertionError(url)
    return get


def test_stable_picks_highest_version_tag(monkeypatch):
    monkeypatch.setattr(update.requests, "get", fake_github(["v0.9.0", "v0.10.1", "nightly", "v0.2.0"]))
    cfg = Config(vault=Path("/tmp/v"))
    t = update.target(cfg)
    assert t["version"] == "v0.10.1" and t["url"].endswith("/archive/refs/tags/v0.10.1.zip") and not t["fallback"]


def test_stable_falls_back_to_latest_without_tags(monkeypatch):
    monkeypatch.setattr(update.requests, "get", fake_github([]))
    cfg = Config(vault=Path("/tmp/v"))
    t = update.target(cfg)
    assert t["version"] == "abcdef123456" and t["url"].endswith("/heads/master.zip") and t["fallback"]
    assert "No stable release" in update.status(cfg)["message"]


def test_status_and_daily_check(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(update.requests, "get", fake_github(["v0.1.0", "v0.2.0"]))
    cfg = Config(vault=tmp_path / "vault", installed_version="v0.1.0")
    st = update.status(cfg)
    assert st["available"] and "version v0.2.0" in st["message"]
    now = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)
    with db.connect(tmp_path / "t.sqlite") as conn:
        assert "update is available" in update.check_daily(conn, cfg, now)
        monkeypatch.setattr(update.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked GitHub twice")))
        assert "update is available" in update.check_daily(conn, cfg, now)


def test_run_installs_channel_target_and_pins(monkeypatch):
    monkeypatch.setattr(update.requests, "get", fake_github(["v0.2.0"]))
    installed = []
    monkeypatch.setattr(update, "install", lambda url: installed.append(url) or True)
    monkeypatch.setattr(update, "_reschedule", lambda cfg: "rescheduled")
    monkeypatch.setattr(update.cfgmod, "save", lambda cfg, path=None: None)
    cfg = Config(vault=Path("/tmp/v"))
    assert "Installed Oso v0.2.0 (stable)" in update.run(cfg)
    assert "already at v0.2.0" in update.run(cfg)
    cfg.channel = "latest"
    assert "(latest)" in update.run(cfg)
    assert "Installed Oso v0.1.0 (pinned)" in update.run(cfg, version="v0.1.0")
    assert installed[-1].endswith("/tags/v0.1.0.zip")
    update.run(cfg, version="0123456789abcdef")
    assert installed[-1].endswith("/archive/0123456789abcdef.zip")


def test_github_unreachable_is_plain(monkeypatch):
    def boom(*a, **k):
        raise update.requests.ConnectionError("no network")
    monkeypatch.setattr(update.requests, "get", boom)
    cfg = Config(vault=Path("/tmp/v"))
    assert not update.status(cfg)["known"]
    assert update.run(cfg).startswith("Could not reach GitHub")


def test_background_install_says_so_and_skips_reschedule(monkeypatch):
    monkeypatch.setattr(update.requests, "get", fake_github(["v0.2.0"]))
    monkeypatch.setattr(update, "install", lambda url: False)
    monkeypatch.setattr(update, "_reschedule", lambda cfg: (_ for _ in ()).throw(AssertionError("rescheduled")))
    monkeypatch.setattr(update.cfgmod, "save", lambda cfg, path=None: None)
    cfg = Config(vault=Path("/tmp/v"))
    out = update.run(cfg)
    assert "installing in the background" in out and "restart the Claude app" in out
    assert cfg.installed_version == "v0.2.0"


def test_windows_script_quotes_paths():
    text = update._WIN_SCRIPT.format(log="C:\\Users\\O''Neil\\update.log", pid=42, uv="uv.exe", url="https://x/y.zip")
    assert "Wait-Process -Id 42" in text and "'C:\\Users\\O''Neil\\update.log'" in text
    assert r"-match '\\tools\\oso\\'" in text


def test_record_does_not_reinstall(monkeypatch):
    monkeypatch.setattr(update, "install", lambda url: (_ for _ in ()).throw(AssertionError("installed")))
    monkeypatch.setattr(update.cfgmod, "save", lambda cfg, path=None: None)
    cfg = Config(vault=Path("/tmp/v"))
    assert "v0.2.0" in update.record(cfg, "v0.2.0") and cfg.installed_version == "v0.2.0"
