"""Mirror a course's Google Drive folder into the vault.

Google Drive for Desktop keeps a local copy of the student's Drive. Point a course at the folder the
professor shares (`oso set-drive-folder CODE path`) and every sync copies new or changed files into
`Courses/<folder>/Drive/`, where the converter turns Office files and PDFs into Markdown.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .config import Config

log = logging.getLogger("oso.drive")

MAX_MB = 50
SKIP_SUFFIXES = {".gform", ".gmap", ".gsite", ".tmp"}


def mirror(cfg: Config) -> int:
    copied = 0
    for c in cfg.courses:
        if not c.drive_folder:
            continue
        src_root = Path(c.drive_folder)
        if not src_root.is_dir():
            log.warning("Drive folder for %s is not available: %s", c.name, src_root)
            continue
        dest_root = cfg.vault / "Courses" / c.folder / "Drive"
        for src in src_root.rglob("*"):
            if not src.is_file() or src.suffix.lower() in SKIP_SUFFIXES or src.name.startswith("."):
                continue
            if src.stat().st_size > MAX_MB * 1024 * 1024:
                continue
            dest = dest_root / src.relative_to(src_root)
            if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                copied += 1
            except OSError as e:
                log.warning("could not copy %s: %s", src.name, type(e).__name__)
    return copied
