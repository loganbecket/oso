"""One piece of Oso's work at a time: the regular check and the folder watcher never run over each other."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from . import config as cfgmod

STALE_SECONDS = 30 * 60  # a lock older than this was left by a run that died; take it over


@contextmanager
def held(wait_seconds: float = 600, path: Path | None = None):
    """Yields True once Oso's work lock is held, or False if it could not be had within wait_seconds."""
    p = path or cfgmod.data_dir() / "work.lock"
    deadline = time.monotonic() + wait_seconds
    got = False
    while True:
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            got = True
            break
        except FileExistsError:
            try:
                if time.time() - p.stat().st_mtime > STALE_SECONDS:
                    p.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                break
            time.sleep(2)
    try:
        yield got
    finally:
        if got:
            p.unlink(missing_ok=True)
