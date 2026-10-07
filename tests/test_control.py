"""Managing Oso from Claude: the status panel's lines, the actions behind its buttons and tools, one window at a
time, and the Start menu shortcut."""

import os
import sys
from pathlib import Path

import pytest

from oso import actions, config as cfgmod, db, doctor, mcp_server, shortcut
from oso.config import Config


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    cfg = Config(vault=tmp_path / "vault")
    cfg.vault.mkdir()
    cfgmod.save(cfg)
    return cfg, data


def test_status_lines_are_plain_and_carry_their_fix(env, monkeypatch):
    from oso import gcal, update, watch

    monkeypatch.setattr(watch, "alive", lambda: False)
    monkeypatch.setattr(gcal, "connected", lambda: False)
    monkeypatch.setattr(update, "status", lambda cfg: {"known": True, "available": True, "message": "Oso v9.9.9 is out."})
    lines = actions.status()
    by_action = {c["action"]: c for c in lines if c["action"]}
    assert {"sync", "fix", "update", "connect_calendar", "connect_canvas"} <= set(by_action)
    assert all(c["action"] in doctor.ACTIONS for c in by_action.values())
    for c in by_action.values():  # the button replaces the terminal hint
        assert "'oso " not in c["text"] and "--fix" not in c["text"], c["text"]
        assert c["status"] in ("warn", "fail")
    assert all(c["action"] is None for c in lines if c["status"] == "ok")


def test_status_fine_states_have_no_buttons(env, monkeypatch):
    from oso import gcal, update, watch

    monkeypatch.setattr(watch, "alive", lambda: True)
    monkeypatch.setattr(gcal, "connected", lambda: True)
    monkeypatch.setattr(update, "status", lambda cfg: {"known": True, "available": False, "message": "Oso is up to date."})
    lines = actions.status()
    texts = " ".join(c["text"] for c in lines if c["status"] == "ok")
    assert "Google Calendar connected" in texts and "Folder watcher is running" in texts and "up to date" in texts


def test_doctor_report_still_shows_terminal_hints(env, monkeypatch):
    from oso import watch

    monkeypatch.setattr(watch, "alive", lambda: False)
    assert any("oso doctor --fix" in text for _, text in doctor.run())


def test_health_check_sentences(env, monkeypatch):
    monkeypatch.setattr(doctor, "checks", lambda fix=False: [{"status": "ok", "text": "fine", "action": None}])
    assert actions.health_check() == "Everything checks out."
    monkeypatch.setattr(doctor, "checks", lambda fix=False: [{"status": "warn", "text": "No sync yet.", "action": "sync"}])
    assert actions.health_check(fix=True).endswith("- No sync yet.")


def test_sync_and_transcribe_start_in_the_background(env, monkeypatch):
    started = []
    monkeypatch.setattr(actions, "_start", lambda *a: started.append(a))
    assert "background" in actions.sync_now()
    assert "background" in actions.transcribe_now()
    assert started == [("sync",), ("transcribe",)]


def test_backup_needs_a_folder(env):
    assert "No backup folder" in actions.backup_now()


def test_settings_window_opens_once(env, monkeypatch):
    _, data = env
    started = []
    monkeypatch.setattr(actions, "_start", lambda *a: started.append(a))
    assert "opening" in actions.open_settings()
    assert started == [("settings",)]
    # The window records itself while open; a second request brings it to the front instead.
    actions.window_pid_path().write_text(str(os.getpid()))
    assert "brought to the front" in actions.open_settings()
    assert started == [("settings",)] and actions.raise_request_path().exists()
    # A window that closed without cleaning up doesn't block a new one.
    actions.window_pid_path().write_text("999999999")
    actions.open_settings()
    assert started == [("settings",), ("settings",)]


def test_tools_return_what_the_buttons_return(env, monkeypatch):
    monkeypatch.setattr(actions, "_start", lambda *a: None)
    monkeypatch.setattr(doctor, "checks", lambda fix=False: [{"status": "ok", "text": "fine", "action": None}])
    assert mcp_server.sync_now() == actions.sync_now()
    assert mcp_server.run_health_check(fix=True) == actions.health_check(fix=True)
    assert mcp_server.oso_status() == actions.status()
    assert mcp_server.backup_now() == actions.backup_now()
    assert "opening" in mcp_server.open_settings()


@pytest.mark.skipif(sys.platform in ("win32", "darwin"), reason="the Linux shortcut")
def test_shortcut_opens_the_window_without_a_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert shortcut.create() is None
    text = (tmp_path / "applications" / "oso.desktop").read_text()
    assert "-m oso settings" in text and "Terminal=false" in text
    assert shortcut.create() is None  # refreshed on every update


def test_macos_shortcut(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    app = tmp_path / "Applications" / "Oso.app"
    shortcut._macos(app)
    launcher = app / "Contents" / "MacOS" / "Oso"
    assert "-m oso settings" in launcher.read_text() and os.access(launcher, os.X_OK)
    assert "<string>Oso</string>" in (app / "Contents" / "Info.plist").read_text()


def test_windows_shortcut_command(tmp_path, monkeypatch):
    calls = []

    class R:
        returncode = 0

    monkeypatch.setattr(shortcut.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or R())
    assert shortcut._windows(tmp_path / "Programs" / "Oso.lnk") is None
    script = calls[0][-1]
    assert "WScript.Shell" in script and "-m oso settings" in script and "Oso.lnk" in script
    assert "$s.Hotkey = 'Ctrl+Alt+O'" in script


def test_strong_bar_moves_from_the_old_default(tmp_path):
    from oso.config import _strong_percent

    assert _strong_percent({}) == 95
    assert _strong_percent({"strong_percent": 80}) == 95  # saved under the old default
    assert _strong_percent({"strong_percent": 85}) == 85  # chosen by the student
    assert _strong_percent({"strong_percent": 80, "settings_version": 2}) == 80  # chosen after the change
