"""Handwritten pages: from a PDF or photo to the transcription queue.

Notebooks pulled from the tablet land in `Courses/<folder>/Handwriting/` (see connectors/remarkable_usb.py).
Scans and photos the student saves there (for example from a phone scanning app through Google Drive)
are treated the same. Scans anywhere else are ignored: every page belongs to a course. This module renders
each PDF page to a PNG under a `pages/<notebook>/` folder beside the PDF, skips blank pages, and queues
the rest with their course. `oso transcribe` (or the transcribe skill) reads the queue, writes the
Markdown note into the course's Notes folder, and marks pages done.
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
    done_at     TEXT,
    course      TEXT
);
"""

IMAGE_EXT = {".png", ".jpg", ".jpeg"}


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pages)")}
    if "course" not in cols:
        conn.execute("ALTER TABLE pages ADD COLUMN course TEXT")


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)


def roots(cfg: Config) -> list[tuple[Path, str]]:
    """(folder, course code) for every place handwriting can land: each course's Handwriting folder."""
    return [(cfg.vault / "Courses" / c.folder / "Handwriting", c.code) for c in cfg.courses]


def queue_new(conn: sqlite3.Connection, cfg: Config, scale: float | None = None) -> int:
    """Render any new PDF or image in a handwriting folder into page PNGs and queue them.

    Blank pages are recorded as 'blank' and never sent anywhere. Returns the number queued."""
    ensure(conn)
    queued = 0
    for folder, course in roots(cfg):
        if not folder.is_dir():
            continue
        for src in sorted(folder.rglob("*")):
            if not src.is_file() or "pages" in src.relative_to(folder).parts or "Transcripts" in src.relative_to(folder).parts:
                continue
            pages_dir = src.parent / "pages"
            kind = _kind(src)
            if kind == "pdf":
                queued += _queue_pdf(conn, cfg, src, pages_dir, scale, course)
            elif kind == "image":
                queued += _queue_image(conn, cfg, src, course)
    return queued


def _kind(src: Path) -> str | None:
    """'pdf', 'image', or None. Files with no extension (some phone share sheets save scans that way)
    are recognized by their first bytes."""
    ext = src.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in IMAGE_EXT:
        return "image"
    if ext:
        return None
    try:
        with src.open("rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff"):
        return "image"
    return None


def is_blank(png: Path, ink_fraction: float = 0.002) -> bool:
    """True when fewer than ink_fraction of the pixels are dark: an empty or nearly empty page."""
    from PIL import Image

    with Image.open(png) as im:
        g = im.convert("L")
        if g.width > 400:
            g = g.resize((400, max(1, int(g.height * 400 / g.width))))
        hist = g.histogram()
    dark = sum(hist[:128])
    total = sum(hist)
    return total == 0 or dark / total < ink_fraction


def _render_scale(doc, cfg: Config, scale: float | None) -> float:
    if scale:
        return scale
    try:
        h = doc[0].get_height()
    except Exception:  # noqa: BLE001
        return 2.0
    return max(0.5, min(4.0, cfg.render_height_px / h)) if h else 2.0


def _queue_pdf(conn: sqlite3.Connection, cfg: Config, src: Path, pages_dir: Path, scale: float | None, course: str | None) -> int:
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
    factor = _render_scale(doc, cfg, scale)
    count = 0
    for i in range(len(doc)):
        if i + 1 in known:
            continue  # pages already transcribed; a notebook only grows at the end
        out = out_dir / f"p{i + 1:03d}.png"
        doc[i].render(scale=factor).to_pil().save(out)
        status = "blank" if is_blank(out) else "pending"
        conn.execute(
            "INSERT OR IGNORE INTO pages (path, notebook, page, source_file, queued_at, course, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_rel(cfg, out), notebook, i + 1, _rel(cfg, src), now_iso(), course, status),
        )
        if status == "pending":
            count += 1
    (out_dir / ".mtime").write_text(str(src.stat().st_mtime))
    return count


def _queue_image(conn: sqlite3.Connection, cfg: Config, src: Path, course: str | None) -> int:
    rel = _rel(cfg, src)
    if conn.execute("SELECT 1 FROM pages WHERE path = ?", (rel,)).fetchone():
        return 0
    status = "blank" if is_blank(src) else "pending"
    conn.execute(
        "INSERT INTO pages (path, notebook, page, source_file, queued_at, course, status) VALUES (?, ?, 1, ?, ?, ?, ?)",
        (rel, src.stem, rel, now_iso(), course, status),
    )
    return 1 if status == "pending" else 0


def pending(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    ensure(conn)
    rows = conn.execute(
        "SELECT path, notebook, page, source_file, queued_at, course FROM pages WHERE status = 'pending' AND course IS NOT NULL ORDER BY course, notebook, page LIMIT ?",
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
