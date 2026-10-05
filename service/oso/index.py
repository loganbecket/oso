"""Full-text index over the vault's Markdown, chunked by heading, in SQLite FTS5.

Rebuilt incrementally: a file is reindexed only when its modification time changes.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import notes
from .config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS indexed_files (
    path   TEXT PRIMARY KEY,
    mtime  REAL NOT NULL,
    course TEXT,
    type   TEXT,
    title  TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    path UNINDEXED, course UNINDEXED, type UNINDEXED, title, heading, body, tokenize = 'porter unicode61'
);
"""

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
SKIP_NAMES = {"Today.md", "Dashboard.md"}


def ensure(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def rebuild(conn: sqlite3.Connection, cfg: Config) -> dict[str, int]:
    ensure(conn)
    seen: set[str] = set()
    counts = {"indexed": 0, "removed": 0}
    known = {r["path"]: r["mtime"] for r in conn.execute("SELECT path, mtime FROM indexed_files")}
    for file in cfg.vault.rglob("*.md"):
        if file.name in SKIP_NAMES or any(part.startswith(".") for part in file.parts):
            continue
        rel = str(file.relative_to(cfg.vault))
        seen.add(rel)
        mtime = file.stat().st_mtime
        if known.get(rel) == mtime:
            continue
        _index_file(conn, cfg, file, rel, mtime)
        counts["indexed"] += 1
    for rel in set(known) - seen:
        conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
        conn.execute("DELETE FROM indexed_files WHERE path = ?", (rel,))
        counts["removed"] += 1
    return counts


def _index_file(conn: sqlite3.Connection, cfg: Config, file: Path, rel: str, mtime: float) -> None:
    text = file.read_text(encoding="utf-8", errors="replace")
    fm, body = notes.read_front_matter(text)
    course = fm.get("course") or _course_from_rel(cfg, rel)
    kind = fm.get("type")
    title = fm.get("title") or _first_heading(body) or file.stem
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
    for heading, chunk in split_sections(body):
        if chunk.strip():
            conn.execute(
                "INSERT INTO chunks (path, course, type, title, heading, body) VALUES (?, ?, ?, ?, ?, ?)",
                (rel, course, kind, title, heading, chunk.strip()),
            )
    conn.execute(
        "INSERT OR REPLACE INTO indexed_files (path, mtime, course, type, title) VALUES (?, ?, ?, ?, ?)",
        (rel, mtime, course, kind, title),
    )


def split_sections(body: str, max_chars: int = 2500) -> list[tuple[str, str]]:
    """(heading, text) pairs; long sections are split into pieces that keep the heading."""
    out: list[tuple[str, str]] = []
    pos = 0
    heading = ""
    for m in _HEADING.finditer(body):
        _emit(out, heading, body[pos:m.start()], max_chars)
        heading = m.group(2).strip()
        pos = m.end()
    _emit(out, heading, body[pos:], max_chars)
    return out


def _emit(out: list[tuple[str, str]], heading: str, text: str, max_chars: int) -> None:
    text = text.strip()
    while len(text) > max_chars:
        cut = text.rfind("\n\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        out.append((heading, text[:cut]))
        text = text[cut:].strip()
    if text:
        out.append((heading, text))


def search(conn: sqlite3.Connection, query: str, course: str | None = None, limit: int = 10) -> list[dict]:
    ensure(conn)
    q = _fts_query(query)
    sql = """SELECT path, course, type, title, heading, snippet(chunks, 5, '**', '**', ' … ', 40) AS snippet, bm25(chunks) AS rank
             FROM chunks WHERE chunks MATCH ?"""
    params: list = [q]
    if course:
        sql += " AND course = ?"
        params.append(course)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _fts_query(query: str) -> str:
    words = re.findall(r"[\w'-]+", query)
    return " ".join(f'"{w}"' for w in words) or '""'


def _first_heading(body: str) -> str | None:
    m = _HEADING.search(body)
    return m.group(2).strip() if m else None


def _course_from_rel(cfg: Config, rel: str) -> str | None:
    parts = Path(rel).parts
    if len(parts) >= 2 and parts[0] == "Courses":
        for c in cfg.courses:
            if c.folder == parts[1]:
                return c.code
    return None
