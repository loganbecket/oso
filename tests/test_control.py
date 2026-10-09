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
    from oso import secrets

    monkeypatch.setattr(secrets, "get", lambda name: None)  # no credential store on the Linux test machine
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


def test_canvas_sign_in_opens_in_its_own_process(env, monkeypatch):
    started = []
    monkeypatch.setattr(actions, "_start", lambda *a: started.append(a))
    assert "sign-in window is opening" in actions.connect_canvas()
    assert started == [("connect-canvas",)]  # the window needs a program's main thread, which the Oso window's buttons don't have


def test_email_uses_the_calendar_client_when_no_file_was_kept(env, monkeypatch):
    import json

    from oso import gcal, secrets

    store = {gcal.TOKEN: json.dumps({"token": "t", "refresh_token": "r", "client_id": "id.apps", "client_secret": "s",
                                     "token_uri": "https://oauth2.googleapis.com/token"})}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    config = gcal.client_config()
    assert config["installed"]["client_id"] == "id.apps" and config["installed"]["client_secret"] == "s"
    assert json.loads(store[gcal.CLIENT]) == config  # kept for next time
    store.clear()
    assert gcal.client_config() is None  # no calendar, no file: then Oso asks for the file


def test_stored_canvas_login_and_quiet_reconnect(env, monkeypatch):
    import json as _json

    from oso import canvas_session, secrets

    store = {}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(secrets, "delete", lambda name: store.pop(name, None))
    started = []
    monkeypatch.setattr(actions, "_start", lambda *a: started.append(a))
    with db.connect() as conn:
        assert not canvas_session.reconnect_quietly(conn)  # nothing stored: he's asked instead
        assert "credential store" in actions.set_canvas_login(" student1 ", 'p"a\\ss')
        assert canvas_session.login() == ("student1", 'p"a\\ss')
        assert canvas_session.reconnect_quietly(conn, now="2026-10-08T10:00:00+00:00")
        assert not canvas_session.reconnect_quietly(conn, now="2026-10-08T10:30:00+00:00")  # at most hourly
        assert canvas_session.reconnect_quietly(conn, now="2026-10-08T11:05:00+00:00")
    assert started == [("connect-canvas", "--quiet")] * 2
    # The fill script carries the values as safe text, whatever characters the password has.
    js = canvas_session.FILL_JS % (_json.dumps("student1"), _json.dumps('p"a\\ss'))
    assert '"p\\"a\\\\ss"' in js and "input[type=password]" in js
    assert "forgot your Canvas sign-in, username, and password" in actions.disconnect_canvas()
    assert canvas_session.login() is None


def test_version_label_shows_the_commit_on_the_latest_channel(monkeypatch):
    import oso

    monkeypatch.setattr(oso, "__version__", "0.10.3")
    assert oso.version_label("v0.10.3") == "Oso v0.10.3"
    assert oso.version_label("1a2b3c4d5e6f") == "Oso v0.10.3 - 1a2b3c4"
    assert oso.version_label(None) == "Oso v0.10.3"


def test_feedback_is_emailed_to_whoever_builds_oso(env, monkeypatch):
    import base64
    from datetime import datetime
    from email import message_from_bytes
    from zoneinfo import ZoneInfo

    import oso
    from oso import feedback, mail

    cfg, _ = env
    cfg.installed_version = "1a2b3c4d5e6f"
    monkeypatch.setattr(oso, "__version__", "0.10.4")
    monkeypatch.setattr(mail, "address", lambda: "student@gmail.com")
    sent = []

    class Session:
        def post(self, url, json):
            sent.append((url, message_from_bytes(base64.urlsafe_b64decode(json["raw"]))))
            return type("R", (), {"raise_for_status": lambda self: None})()

    to = feedback.send(cfg, "your quizzes aren't formatting equations correctly\nso I can't decipher them", "bug",
                       "Equations in quiz questions show as raw code", "quiz 12, Physics, question 3",
                       now=datetime(2026, 10, 8, 21, 5, tzinfo=ZoneInfo("America/New_York")), session=Session())
    url, msg = sent[0]
    assert to == "logan@loganbecket.com" and url.endswith("/messages/send")
    assert msg["To"] == "logan@loganbecket.com" and msg["From"] == "student@gmail.com"
    assert msg["Subject"] == "Oso bug: Equations in quiz questions show as raw code"
    body = msg.get_payload(decode=True).decode()
    assert "Oso v0.10.4 - 1a2b3c4" in body and "quiz 12, Physics, question 3" in body
    assert "> your quizzes aren't formatting equations correctly\n> so I can't decipher them" in body
    assert not (cfg.vault / "Oso" / "Feedback").exists()
    with pytest.raises(ValueError, match="bug or idea"):
        feedback.send(cfg, "x", "rant", "y", session=Session())


def test_feedback_without_permission_to_send_says_so(env, monkeypatch):
    from oso import feedback, mail

    cfg, _ = env
    monkeypatch.setattr(mail, "connected", lambda: True)
    monkeypatch.setattr(mail, "can_send", lambda: False)
    with pytest.raises(feedback.NotSent, match="sign in to Gmail once more"):
        feedback.send(cfg, "x", "bug", "y")


def test_unprompted_complaints_are_asked_about_first():
    from oso.tutor import SERVER_INSTRUCTIONS

    assert "Want me to pass that on as feedback?" in SERVER_INSTRUCTIONS
    skill = (Path(__file__).parent.parent / "service" / "oso" / "skills" / "oso-feedback.md").read_text()
    assert "Save it only if he says yes" in skill
