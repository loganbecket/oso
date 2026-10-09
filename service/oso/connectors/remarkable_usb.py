"""reMarkable over USB, no cloud.

When the tablet is plugged into the laptop with "USB web interface" turned on (Settings, Storage),
it serves a small web server at http://10.11.99.1.

Organization mirrors the vault: a folder on the tablet named exactly like a course folder in the
vault (for example "Physics") is that course's handwriting. Every notebook inside it that changed
since the last pull is downloaded, as a PDF rendered by the tablet itself, into
`Courses/<folder>/Handwriting/`, keeping any sub-folders. Notebooks anywhere else on the tablet are
ignored, so personal notes never enter the vault. An optional root folder (config `remarkable_folder`)
holds the course folders if the student prefers them grouped.

If the tablet is not plugged in, nothing happens and nothing is reported as a failure.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import requests

from .. import notes
from ..config import Config
from ..db import now_iso

log = logging.getLogger("oso.remarkable")

NAME = "remarkable_usb"
BASE = "http://10.11.99.1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS remarkable_docs (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    folder        TEXT,
    modified      TEXT,
    downloaded_at TEXT,
    file          TEXT
);
"""


class NotConnected(Exception):
    pass


class RemarkableUsb:
    name = NAME

    def __init__(self, cfg: Config, base: str = BASE, timeout: float = 20.0):
        self.cfg = cfg
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()

    # The connector protocol: fetch() returns items. The tablet has no deadlines, so it returns none;
    # the real work is pull().
    def fetch(self) -> list:
        return []

    def connected(self) -> bool:
        try:
            r = self.s.get(f"{self.base}/documents/", timeout=3)
            return r.ok
        except requests.RequestException:
            return False

    def pull(self, conn: sqlite3.Connection) -> int:
        """Download every notebook that changed since the last pull. Returns how many were downloaded."""
        from .. import schema

        schema.apply(conn)
        if not self.connected():
            raise NotConnected()
        folders = {c.folder_name.lower(): c for c in self.cfg.courses if not c.finished}
        pulled = 0
        for doc in self._walk():
            if doc.get("Type") != "DocumentType":
                continue
            if doc.get("fileType") not in (None, "", "notebook"):
                continue  # imported PDFs and books are not handwriting
            parts = doc["_path"].split("/")
            if self.cfg.remarkable_folder:
                if not parts or parts[0].lower() != self.cfg.remarkable_folder.lower():
                    continue
                parts = parts[1:]
            if len(parts) < 2 or parts[0].lower() not in folders:
                continue  # not inside a course folder
            course = folders[parts[0].lower()]
            sub = [notes.safe_name(p) for p in parts[1:-1]]
            dest = self.cfg.vault / "Courses" / course.folder / "Handwriting"
            for p in sub:
                dest = dest / p
            dest.mkdir(parents=True, exist_ok=True)
            doc_id = doc["ID"]
            modified = doc.get("ModifiedClient") or ""
            row = conn.execute("SELECT modified FROM remarkable_docs WHERE id = ?", (doc_id,)).fetchone()
            if row is not None and row["modified"] == modified:
                continue
            name = notes.safe_name(doc.get("VissibleName") or doc_id)
            target = dest / f"{name}.pdf"
            try:
                self._download(doc_id, target)
            except requests.RequestException as e:
                log.warning("could not download %s: %s", name, type(e).__name__)
                continue
            conn.execute(
                """INSERT INTO remarkable_docs (id, name, folder, modified, downloaded_at, file) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name = excluded.name, folder = excluded.folder, modified = excluded.modified,
                     downloaded_at = excluded.downloaded_at, file = excluded.file""",
                (doc_id, name, doc["_path"], modified, now_iso(), str(target.relative_to(self.cfg.vault))),
            )
            pulled += 1
        return pulled

    def _walk(self, folder_id: str = "", path: str = "") -> list[dict]:
        r = self.s.get(f"{self.base}/documents/{folder_id}", timeout=self.timeout)
        r.raise_for_status()
        out: list[dict] = []
        for item in r.json():
            item["_path"] = f"{path}{item.get('VissibleName', '')}"
            if item.get("Type") == "CollectionType":
                out.extend(self._walk(item["ID"], item["_path"] + "/"))
            else:
                out.append(item)
        return out

    def _download(self, doc_id: str, target: Path) -> None:
        last: Exception | None = None
        for suffix in ("pdf", "placeholder"):
            try:
                with self.s.get(f"{self.base}/download/{doc_id}/{suffix}", stream=True, timeout=120) as r:
                    r.raise_for_status()
                    tmp = target.with_suffix(".pdf.part")
                    with tmp.open("wb") as f:
                        for chunk in r.iter_content(1 << 16):
                            f.write(chunk)
                    tmp.replace(target)
                    return
            except requests.RequestException as e:
                last = e
        if last:
            raise last


def last_pull(conn: sqlite3.Connection) -> datetime | None:
    try:
        row = conn.execute("SELECT MAX(downloaded_at) AS t FROM remarkable_docs").fetchone()
    except sqlite3.OperationalError:
        return None
    return datetime.fromisoformat(row["t"]) if row and row["t"] else None
