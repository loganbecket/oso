"""Watch the course folders and take in new files within seconds, instead of waiting for the next check.

The operating system tells Oso when files change (Windows, macOS, and Linux all do this without Oso
having to look), so the watcher sits idle until something arrives. It then waits for things to settle
(files dropped in batches, or still being copied by Google Drive) and runs the local part of a check:
filing clippings, making text copies, reading books, queuing handwriting, updating search and the
profile, and having Claude read hard pages. Nothing goes to Canvas or the calendar; the regular check
does that. Claude reads only pages that are waiting, the same ones the regular check would have sent.

Oso's own output (text copies, chapter notes, page images, transcribed notes) is ignored, so the watcher
never sets itself off. If a change is ever missed (some cloud drives don't report every change), the
regular check catches it within the interval.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config as cfgmod
from . import vault

log = logging.getLogger("oso.watch")

SETTLE_SECONDS = 20     # quiet time after the last change before taking files in
HEARTBEAT_SECONDS = 300
IGNORED_PARTS = (set(vault.SKIP_PARTS) - {"Handwriting"}) | set(vault.GENERATED_PARTS)  # Oso fills these itself
_CONVERTED = re.compile(r"\.(pdf|docx?|pptx?|xlsx?|odt|odp|ods|rtf|epub|gdoc|gsheet|gslides|html?)\.md$", re.IGNORECASE)
_CHAPTER = re.compile(r"^\d\d .+\.md$")
_TEMP = re.compile(r"(^~\$|^\.~lock|\.part$|\.tmp$|\.crdownload$|\.download$|^\.)", re.IGNORECASE)


def matters(cfg: cfgmod.Config, path: Path) -> bool:
    """True for a change the student (or Drive) made; False for Oso's own output and temporary files."""
    try:
        rel = path.resolve().relative_to(cfg.vault.resolve())
    except ValueError:
        return False
    parts = rel.parts
    if not parts or parts[0] not in ("Courses", "Clippings"):
        return False
    name = parts[-1]
    if IGNORED_PARTS & set(parts) or _TEMP.search(name) or _CONVERTED.search(name):
        return False
    if name.lower().endswith(".md"):
        state = vault.ownership(path, _legacy)
        if state == "ours":
            return False  # Oso's own note (chapter notes, Book.md, transcribed handwriting), untouched by him
        if state == "missing":  # just deleted or not yet readable: go by where it was and what it was called
            if "Books" in parts and len(parts[parts.index("Books") + 1:]) == 2 and (name == "Book.md" or _CHAPTER.match(name)):
                return False
            if "Notes" in parts and re.match(r"^\d{4}-\d\d-\d\d .+\.md$", name):
                return False
    return True


def _legacy(fm: dict) -> bool:
    return vault.textbook_note(fm) or vault.book_index(fm) or vault.transcribed_note(fm) or vault.converted_copy(fm)


class Settler:
    """Collects changes and says when they have been quiet for SETTLE_SECONDS."""

    def __init__(self, settle: float = SETTLE_SECONDS, clock=time.monotonic):
        self.settle, self.clock = settle, clock
        self.last: float | None = None
        self.lock = threading.Lock()

    def touch(self) -> None:
        with self.lock:
            self.last = self.clock()

    def due(self) -> bool:
        with self.lock:
            if self.last is not None and self.clock() - self.last >= self.settle:
                self.last = None
                return True
            return False


def ingest() -> dict:
    from . import sync

    cfg = cfgmod.load()
    return sync.ingest(cfg, datetime.now(cfg.tz))


def heartbeat_path() -> Path:
    return cfgmod.data_dir() / "watch.heartbeat"


def alive(max_age: float = HEARTBEAT_SECONDS * 3) -> bool:
    p = heartbeat_path()
    return p.exists() and time.time() - p.stat().st_mtime < max_age


def main() -> None:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    logging.basicConfig(filename=str(cfgmod.data_dir() / "watch.log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = cfgmod.load()
    settler = Settler()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory and event.event_type == "modified":
                return
            for p in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
                if p and matters(cfg, Path(p)):
                    settler.touch()
                    return

    observer = Observer()
    for sub in ("Courses", "Clippings"):
        folder = cfg.vault / sub
        folder.mkdir(parents=True, exist_ok=True)
        observer.schedule(Handler(), str(folder), recursive=True)
    observer.start()
    log.info("watching %s", cfg.vault)
    beat = 0.0
    try:
        while True:
            time.sleep(2)
            if time.monotonic() - beat > HEARTBEAT_SECONDS:
                heartbeat_path().touch()
                beat = time.monotonic()
            if settler.due():
                try:
                    log.info("new files: %s", ingest())
                except Exception as e:  # noqa: BLE001
                    log.warning("could not take in new files: %s", type(e).__name__)
                cfg = cfgmod.load()  # pick up courses added meanwhile
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    try:
        main()
    except cfgmod.ConfigError:
        sys.exit(0)  # not set up yet; the scheduled task tries again at next sign-in
