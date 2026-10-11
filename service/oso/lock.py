"""One piece of Oso's work at a time: the regular check and the folder watcher never run over each other."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from . import config as cfgmod

STALE_SECONDS = 30 * 60  # a lock older than this was left by a run that died; take it over


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _owner(p: Path) -> str | None:
    """What the lock file says (the owner's pid), or None when it can't be read this instant."""
    try:
        return p.read_text().strip()
    except OSError:
        return None


def _stale(p: Path, owner: str | None) -> bool:
    """A lock left by a run that is no longer running. A live owner keeps it however old it is; only when
    the owner can't be read at all does age decide."""
    if owner is None or not owner.isdigit():
        try:
            return time.time() - p.stat().st_mtime > STALE_SECONDS
        except OSError:
            return False
    return not _alive(int(owner))


@contextmanager
def held(wait_seconds: float = 600, path: Path | None = None):
    """Yields True once Oso's work lock is held, or False if it could not be had within wait_seconds."""
    p = path or cfgmod.data_dir() / "work.lock"
    mine = str(os.getpid())
    deadline = time.monotonic() + wait_seconds
    got = False
    while True:
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, mine.encode())
            os.close(fd)
            got = True
            break
        except FileExistsError:
            try:
                owner = _owner(p)
                if _stale(p, owner):
                    if _owner(p) == owner:  # still the same dead owner, not a fresh lock taken meanwhile
                        p.unlink(missing_ok=True)  # left by a run that was stopped (an update, a crash)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                break
            time.sleep(2)
    try:
        yield got
    finally:
        if got and _owner(p) == mine:  # never remove a lock another run has taken since
            p.unlink(missing_ok=True)
