"""The setup window: which steps are done, and clicking through it for real (skipped without a display)."""

from pathlib import Path

import pytest
from oso import config as cfgmod
from oso import secrets, setup_gui


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cfgmod, "config_path", lambda: path)
    store: dict = {}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    return path


def test_settings_from_before_setup_count_as_set_up(settings_file: Path, tmp_path: Path):
    settings_file.write_text(f'vault = "{tmp_path.as_posix()}"\n', encoding="utf-8")
    assert cfgmod.load().setup_finished
    assert not setup_gui.needs_setup()


def test_steps_are_recorded_until_every_one_is_done_or_skipped(settings_file: Path, tmp_path: Path):
    assert setup_gui.needs_setup()
    cfg = setup_gui.begin(tmp_path / "Vault", "America/Chicago", setup_gui.BEFORE_FOLDER)
    assert (tmp_path / "Vault" / "Clippings").is_dir()
    assert cfg.timezone == "America/Chicago" and not cfg.setup_finished
    assert setup_gui.remaining(cfgmod.load())[0] == "canvas_feed"

    # A course Claude adds while the window is open survives the next step being recorded.
    added = cfgmod.load()
    added.courses.append(cfgmod.Course("PHYS-110", "Physics", "2026 Fall/Physics"))
    cfgmod.save(added)
    for step in setup_gui.STEP_IDS[setup_gui.STEP_IDS.index("canvas_feed"):-1]:
        setup_gui.record(step)
    cfg = cfgmod.load()
    assert setup_gui.remaining(cfg) == ["remarkable"] and [c.code for c in cfg.courses] == ["PHYS-110"]

    assert setup_gui.record("remarkable").setup_finished
    assert not setup_gui.needs_setup()
    assert "setup_steps" not in settings_file.read_text(encoding="utf-8")


def test_dont_show_again_ends_setup(settings_file: Path, tmp_path: Path):
    setup_gui.begin(tmp_path / "Vault", "America/New_York")
    assert setup_gui.stop_showing().setup_finished
    assert not setup_gui.needs_setup()


def test_local_timezone_is_a_real_zone():
    from zoneinfo import ZoneInfo

    ZoneInfo(setup_gui.local_timezone())


def _display():
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display")
    return tk


def _find(widget, kind, text=None):
    for w in widget.winfo_children():
        if isinstance(w, kind) and (text is None or str(w.cget("text")) == text):
            return w
        found = _find(w, kind, text)
        if found is not None:
            return found
    return None


def test_window_walks_through_setup(settings_file: Path, tmp_path: Path, monkeypatch):
    _display()
    from tkinter import ttk

    from oso import canvas_session

    monkeypatch.setattr(setup_gui, "_start_checking", lambda cfg: None)
    monkeypatch.setattr(canvas_session, "status", lambda conn: "connected")
    from oso import db

    real_connect = db.connect
    monkeypatch.setattr(db, "connect", lambda *a, **k: real_connect(tmp_path / "t.sqlite"))
    monkeypatch.setattr(setup_gui.sys, "platform", "win32")

    wizard = setup_gui.Wizard(None)
    root = wizard.win

    def title() -> str:
        return str(_find(wizard.page, ttk.Label).cget("text"))

    def press(text: str) -> None:
        _find(wizard.page, ttk.Button, text).invoke()
        root.update()

    root.update()
    assert title() == "A Google account"
    while title() != "Choose your vault":  # done before there are settings: kept until the vault is chosen
        press("Done")
    press("Next")
    assert "Choose your vault folder first." in str(wizard.message.cget("text"))
    _find(wizard.page, ttk.Entry).insert(0, str(tmp_path / "Vault"))
    press("Next")
    assert set(setup_gui.BEFORE_FOLDER) <= set(cfgmod.load().setup_steps)
    assert title() == "Your Canvas calendar"
    press("Next")
    assert "Paste the Calendar Feed address first." in str(wizard.message.cget("text"))
    _find(wizard.page, ttk.Entry).insert(0, "https://school.instructure.com/feeds/calendars/user_x.ics")
    press("Next")
    assert secrets.get(secrets.CANVAS_FEED_URL).endswith(".ics")
    assert title() == "Sign in to Canvas"
    for _ in range(40):  # the check runs off the window's thread
        root.update()
        if str(_find(wizard.page, ttk.Button, "Next").cget("state")) == "normal":
            break
        root.after(50)
    press("Next")
    assert title() == "Claude Pro"
    press("Done")
    press("Skip for now")
    assert setup_gui.remaining(cfgmod.load())[0] == "claude_code"
    while title() != "Register your own copy of Oso":
        press("Skip for now")
    press("Skip all of these")
    assert title() == "GroupMe"
    while title() != "You're set up":
        press("Skip for now")
    assert cfgmod.load().setup_finished
    press("Close")
    import gc

    gc.collect()


def test_reminder_resumes_or_goes_away_for_good(settings_file: Path, tmp_path: Path, monkeypatch):
    tk = _display()
    from tkinter import ttk

    setup_gui.begin(tmp_path / "Vault", "America/New_York")
    root = tk.Tk()
    done = []
    setup_gui.offer_resume(root, lambda: done.append(True))
    root.update()
    box = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
    assert "•  Canvas\n" in " ".join(str(w.cget("text")) for w in box.winfo_children()[0].winfo_children() if isinstance(w, ttk.Label))
    _find(box, ttk.Checkbutton, "Don't show this again").invoke()
    _find(box, ttk.Button, "Not now").invoke()
    root.update()
    assert done and not setup_gui.needs_setup()
    root.destroy()
    import gc

    gc.collect()
