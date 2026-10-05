"""Handwritten pages: from the tablet to the transcription queue.

On the reMarkable, "Send" a notebook to Google Drive (or export it) into the vault's
`Inbox/Handwriting` folder. Google Drive for Desktop lands it here as a PDF. This module renders
each PDF page to a PNG under `Inbox/Handwriting/pages/<notebook>/` and queues the pages. The
transcribe skill (a Claude Code run) reads the queue, writes the Markdown note, and marks pages done.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import Config
from .db import now_iso

log = logging.getLogger("oso.handwriting")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    path        TEXT PRIMARY KEY,
    notebook    TEXT NOT NULL,
    page        INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    queued_at   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    note_path   TEXT,
    confidence  REAL,
    done_at     TEXT
);
"""

IMAGE_EXT = {".png", ".jpg", ".jpeg"}


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def inbox(cfg: Config) -> Path:
    return cfg.vault / "Inbox" / "Handwriting"


def queue_new(conn: sqlite3.Connection, cfg: Config, scale: float = 2.0) -> int:
    """Render any new PDF or image in Inbox/Handwriting into page PNGs and queue them."""
    ensure(conn)
    folder = inbox(cfg)
    folder.mkdir(parents=True, exist_ok=True)
    pages_dir = folder / "pages"
    queued = 0
    for src in sorted(folder.iterdir()):
        if not src.is_file():
            continue
        if src.suffix.lower() == ".pdf":
            queued += _queue_pdf(conn, cfg, src, pages_dir, scale)
        elif src.suffix.lower() in IMAGE_EXT:
            queued += _queue_image(conn, cfg, src, pages_dir)
    return queued


def _queue_pdf(conn: sqlite3.Connection, cfg: Config, src: Path, pages_dir: Path, scale: float) -> int:
    notebook = src.stem
    known = {r["page"] for r in conn.execute("SELECT page FROM pages WHERE source_file = ?", (_rel(cfg, src),))}
    if known:
        marker = pages_dir / notebook / ".mtime"
        if marker.exists() and float(marker.read_text() or 0) >= src.stat().st_mtime:
            return 0
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(src))
    except Exception as e:  # noqa: BLE001
        log.warning("could not open %s: %s", src.name, type(e).__name__)
        return 0
    out_dir = pages_dir / notebook
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for i in range(len(doc)):
        if i + 1 in known:
            continue  # pages already transcribed; a notebook only grows at the end
        out = out_dir / f"p{i + 1:03d}.png"
        doc[i].render(scale=scale).to_pil().save(out)
        conn.execute(
            "INSERT OR IGNORE INTO pages (path, notebook, page, source_file, queued_at) VALUES (?, ?, ?, ?, ?)",
            (_rel(cfg, out), notebook, i + 1, _rel(cfg, src), now_iso()),
        )
        count += 1
    (out_dir / ".mtime").write_text(str(src.stat().st_mtime))
    return count


def _queue_image(conn: sqlite3.Connection, cfg: Config, src: Path, pages_dir: Path) -> int:
    rel = _rel(cfg, src)
    if conn.execute("SELECT 1 FROM pages WHERE path = ?", (rel,)).fetchone():
        return 0
    conn.execute(
        "INSERT INTO pages (path, notebook, page, source_file, queued_at) VALUES (?, ?, 1, ?, ?)",
        (rel, src.stem, rel, now_iso()),
    )
    return 1


def pending(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        "SELECT path, notebook, page, source_file, queued_at FROM pages WHERE status = 'pending' ORDER BY notebook, page LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark(conn: sqlite3.Connection, path: str, note_path: str, confidence: float) -> None:
    ensure(conn)
    conn.execute(
        "UPDATE pages SET status = 'done', note_path = ?, confidence = ?, done_at = ? WHERE path = ?",
        (note_path, confidence, now_iso(), path),
    )


def low_confidence(conn: sqlite3.Connection, threshold: float = 0.7, since_hours: int = 48) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        """SELECT path, notebook, page, note_path, confidence FROM pages
           WHERE status = 'done' AND confidence IS NOT NULL AND confidence < ?
             AND done_at >= datetime('now', ?) ORDER BY confidence""",
        (threshold, f"-{since_hours} hours"),
    ).fetchall()
    return [dict(r) for r in rows]


def _rel(cfg: Config, p: Path) -> str:
    return str(p.relative_to(cfg.vault))
