import threading
import time
from pathlib import Path

import pytest

from oso import config as cfgmod, lock, sync, watch
from oso.config import Config, Course


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch):
    c = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    (c.vault / "Courses" / "2026 Fall" / "Physics").mkdir(parents=True)
    (c.vault / "Clippings").mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path / "data")
    (tmp_path / "data").mkdir()
    return c


@pytest.mark.parametrize("rel, expected", [
    ("Courses/2026 Fall/Physics/Lectures/Week 3.pdf", True),
    ("Courses/2026 Fall/Physics/Handwriting/scan.pdf", True),
    ("Courses/2026 Fall/Physics/Books/Serway.pdf", True),
    ("Courses/2026 Fall/Physics/Books/Mechanics/Scans/04.png", True),
    ("Courses/2026 Fall/Physics/Books/Mechanics/Clipped/page.md", True),
    ("Clippings/Syllabus.md", True),
    ("Courses/2026 Fall/Physics/Lectures/Week 3.pdf.md", False),          # Oso's text copy
    ("Courses/2026 Fall/Physics/Books/Serway/03 Forces.md", False),       # Oso's chapter note
    ("Courses/2026 Fall/Physics/Books/Serway/Book.md", False),
    ("Courses/2026 Fall/Physics/Handwriting/pages/scan/p001.png", False),  # Oso's page images
    ("Courses/2026 Fall/Physics/Notes/2026-10-05 Lab notebook.md", False),  # Oso's transcription
    ("Courses/2026 Fall/Physics/Lectures/~$Week 3.docx", False),          # Office's temporary file
    ("Courses/2026 Fall/Physics/Lectures/big.pdf.part", False),
    ("Today.md", False),
    ("Oso/Profile/Physics.md", False),
])
def test_only_his_changes_matter(cfg, rel, expected):
    assert watch.matters(cfg, cfg.vault / rel) is expected


def test_settles_before_taking_files_in():
    t = [0.0]
    s = watch.Settler(settle=20, clock=lambda: t[0])
    assert not s.due()
    s.touch()
    t[0] = 10
    s.touch()           # another file 10 seconds later restarts the wait
    t[0] = 25
    assert not s.due()
    t[0] = 31
    assert s.due() and not s.due()  # once per burst


def test_one_task_at_a_time(cfg):
    with lock.held() as first:
        assert first
        with lock.held(wait_seconds=0) as second:
            assert not second
    with lock.held(wait_seconds=0) as again:
        assert again


def test_ingest_is_local_only(cfg, monkeypatch):
    called = []
    for name in ("file_clippings",):
        monkeypatch.setattr(sync.filing, name, lambda *a: called.append("filing") or 0)
    monkeypatch.setattr(sync.convert, "convert_vault", lambda c: called.append("convert") or [])
    monkeypatch.setattr(sync.books, "process", lambda c, conn: called.append("books") or {})
    monkeypatch.setattr(sync.search, "update", lambda c: called.append("search") or {})
    monkeypatch.setattr(sync.reader, "run", lambda c, conn, now: called.append("reader") or {})
    monkeypatch.setattr(sync, "connectors", lambda *a: (_ for _ in ()).throw(AssertionError("ingest must not reach Canvas")))
    sync.ingest(cfg)
    assert called == ["filing", "convert", "books", "search", "reader", "search"]


def test_the_operating_system_reports_new_files(cfg):
    """The real watcher machinery on this computer: a file dropped in a course folder is noticed."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    seen = threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if watch.matters(cfg, Path(event.src_path)):
                seen.set()

    obs = Observer()
    obs.schedule(Handler(), str(cfg.vault / "Courses"), recursive=True)
    obs.start()
    try:
        time.sleep(0.5)
        (cfg.vault / "Courses" / "2026 Fall" / "Physics" / "new handout.pdf").write_bytes(b"%PDF-1.4")
        assert seen.wait(10)
    finally:
        obs.stop()
        obs.join()


def test_windows_watch_task_runs_windowless_and_restarts():
    from oso import install_windows

    xml = install_windows._WATCH_XML.format(command="C:\\oso\\pythonw.exe", user="PC\\Campbell")
    assert "<Arguments>-m oso.watch</Arguments>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<RestartOnFailure>" in xml and "<UserId>PC\\Campbell</UserId>" in xml


def test_a_lock_left_by_a_stopped_program_is_taken_over(cfg):
    p = cfgmod.data_dir() / "work.lock"
    p.write_text("999999")  # a process that doesn't exist
    with lock.held(wait_seconds=0) as got:
        assert got


def test_a_lock_held_by_a_live_program_is_respected(cfg):
    import os

    p = cfgmod.data_dir() / "work.lock"
    p.write_text(str(os.getpid()))
    with lock.held(wait_seconds=0) as got:
        assert not got
    p.unlink()


def test_windows_check_runs_windowless():
    from oso import install_windows

    xml = install_windows._XML.format(minutes=15, command="C:\\oso\\pythonw.exe", user="PC\\Campbell")
    assert "<Command>C:\\oso\\pythonw.exe</Command><Arguments>-m oso sync</Arguments>" in xml


def test_python_dash_m_oso_runs_the_cli():
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "-m", "oso", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "sync" in r.stdout
