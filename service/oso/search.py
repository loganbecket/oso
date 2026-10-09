"""Search over the vault: built at ingestion so questions are answered fast.

On every sync, each new or changed Markdown note under `Courses/` and `Clippings/` is split into
sections, and each section is stored with a full-text index (exact words, SQLite FTS5) and a meaning
vector from a small local embedding model (bge-small, about 65 MB, run through ONNX Runtime and
downloaded by Oso the first time; no separate program). A query combines both rankings, so a question
about "derivatives" finds a section that only says "rate of change".

The index lives in the data folder, not the vault, and is a disposable copy: delete it and the next
sync rebuilds it. If the model cannot be loaded (for example offline on the very first run), search
falls back to exact words and the vectors are filled in on a later sync.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config as cfgmod
from . import notes, vault
from .config import Config

log = logging.getLogger("oso.search")

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384
ROOTS = ("Courses", "Clippings")
SKIP_PARTS = set(vault.SKIP_PARTS)
CHUNK_CHARS = 1500

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY,
    path    TEXT NOT NULL,
    course  TEXT,
    title   TEXT,
    heading TEXT,
    text    TEXT NOT NULL,
    vec     BLOB
);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title, heading, text, content='chunks', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, title, heading, text) VALUES (new.id, new.title, new.heading, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, title, heading, text) VALUES ('delete', old.id, old.title, old.heading, old.text);
END;
"""


# ---- the embedding model -------------------------------------------------------------------------

_model = None
_model_failed_at: float | None = None
RETRY_MODEL_SECONDS = 600  # a load that failed (offline at startup, say) is tried again after this long


def _embedder():
    """The model, loaded once per process; None if it cannot be loaded right now."""
    import time

    global _model, _model_failed_at
    if _model is None and (_model_failed_at is None or time.monotonic() - _model_failed_at > RETRY_MODEL_SECONDS):
        try:
            from fastembed import TextEmbedding

            _model = TextEmbedding(MODEL, cache_dir=str(cfgmod.data_dir() / "models"))
            _model_failed_at = None
        except Exception as e:  # noqa: BLE001
            log.warning("search model unavailable, using exact words only: %s", type(e).__name__)
            _model_failed_at = time.monotonic()
    return _model


def rebuild(path: Path | None = None) -> None:
    """Throw the index away; the next update rebuilds it from the vault (the index is a copy, never the truth)."""
    p = path or index_path()
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(p) + suffix).unlink(missing_ok=True)
    log.warning("search index rebuilt from scratch")


def embed_passages(texts: list[str]) -> list[bytes] | None:
    import numpy as np

    m = _embedder()
    if m is None:
        return None
    return [np.asarray(v, dtype=np.float32).tobytes() for v in m.embed(texts, batch_size=32)]


def embed_query(text: str):
    import numpy as np

    m = _embedder()
    if m is None:
        return None
    return np.asarray(next(iter(m.query_embed([text]))), dtype=np.float32)


# ---- the index -----------------------------------------------------------------------------------


def index_path() -> Path:
    return cfgmod.data_dir() / "search.sqlite"


@contextmanager
def connect(path: Path | None = None):
    conn = sqlite3.connect(path or index_path(), timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)  # a damaged file fails here; the handle must still be closed (Windows will not delete an open file)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _files(cfg: Config):
    for root in ROOTS:
        base = cfg.vault / root
        if not base.is_dir():
            continue
        for f in base.rglob("*.md"):
            rel = f.relative_to(cfg.vault)
            if SKIP_PARTS & set(rel.parts) or any(p.startswith(".") for p in rel.parts):
                continue
            yield f, rel.as_posix()


def _course_for(cfg: Config, rel: str, fm: dict) -> str | None:
    low = rel.lower()
    for c in sorted(cfg.courses, key=lambda c: len(c.folder), reverse=True):
        if low.startswith(f"courses/{c.folder.lower()}/"):
            return c.code
    return fm.get("course") or None


def update(cfg: Config, path: Path | None = None) -> dict[str, int]:
    """Index new and changed notes, drop deleted ones, and fill in any missing vectors. A damaged index is
    thrown away and built again."""
    try:
        return _update(cfg, path)
    except sqlite3.DatabaseError as e:
        log.warning("search index unreadable (%s); rebuilding", type(e).__name__)
        rebuild(path)
        return {**_update(cfg, path), "rebuilt": 1}


def _update(cfg: Config, path: Path | None = None) -> dict[str, int]:
    counts = {"indexed": 0, "removed": 0, "embedded": 0}
    with connect(path) as conn:
        known = {r["path"]: (r["mtime"], r["size"]) for r in conn.execute("SELECT path, mtime, size FROM files")}
        seen = set()
        for f, rel in _files(cfg):
            seen.add(rel)
            st = f.stat()
            if known.get(rel) == (st.st_mtime, st.st_size):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                _index_file(conn, cfg, rel, text)
            except Exception as e:  # one bad note must never stop the rest of the vault from being indexed
                log.warning("skipped %s while indexing: %s", rel, type(e).__name__)
                continue
            conn.execute("INSERT OR REPLACE INTO files (path, mtime, size) VALUES (?, ?, ?)", (rel, st.st_mtime, st.st_size))
            counts["indexed"] += 1
        for rel in set(known) - seen:
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
            conn.execute("DELETE FROM files WHERE path = ?", (rel,))
            counts["removed"] += 1
        conn.commit()

        while True:
            rows = conn.execute("SELECT id, title, heading, text FROM chunks WHERE vec IS NULL LIMIT 256").fetchall()
            if not rows:
                break
            vecs = embed_passages([_passage(r) for r in rows])
            if vecs is None:
                break
            conn.executemany("UPDATE chunks SET vec = ? WHERE id = ?", [(v, r["id"]) for v, r in zip(vecs, rows)])
            conn.commit()
            counts["embedded"] += len(rows)
    return counts


def _title(fm: dict, stem: str) -> str:
    """The note's title: its own, or book and chapter (or page) for a textbook note, or the file name."""
    if fm.get("title"):
        return str(fm["title"])
    if fm.get("type") == "textbook" and fm.get("book"):
        part = fm.get("chapter") or fm.get("page")
        return f"{fm['book']}, {part}" if part else str(fm["book"])
    return stem


def _index_file(conn: sqlite3.Connection, cfg: Config, rel: str, text: str) -> None:
    fm, body = notes.read_front_matter(text)
    title = _title(fm if isinstance(fm, dict) else {}, Path(rel).stem)
    course = _course_for(cfg, rel, fm if isinstance(fm, dict) else {})
    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
    for heading, chunk in notes.split_sections(body, max_chars=CHUNK_CHARS):
        if chunk.strip():
            conn.execute(
                "INSERT INTO chunks (path, course, title, heading, text) VALUES (?, ?, ?, ?, ?)",
                (rel, course, title, heading, chunk),
            )


def _passage(r) -> str:
    head = " / ".join(x for x in (r["title"], r["heading"]) if x)
    return f"{head}\n{r['text']}" if head else r["text"]


def _fts_query(q: str) -> str:
    words = re.findall(r"\w+", q.lower())
    return " OR ".join(f'"{w}"' for w in words if len(w) > 1)


def query(cfg: Config, q: str, course: str | None = None, limit: int = 8, path: Path | None = None,
          source: str | None = None) -> list[dict]:
    """The best-matching sections, combining exact-word and meaning rankings (reciprocal rank fusion).

    With a course: that course plus the earlier courses it is related to. Without: every course not marked
    finished (finished courses are searched only when named)."""
    import numpy as np

    try:
        return _query(cfg, q, course, limit, path, source, np)
    except sqlite3.DatabaseError as e:
        log.warning("search index unreadable (%s); it will be rebuilt on the next check", type(e).__name__)
        rebuild(path)
        return []


def _query(cfg: Config, q: str, course: str | None, limit: int, path: Path | None, source: str | None, np) -> list[dict]:
    codes = scope(cfg, course)
    if codes is None:
        hidden = sorted(cfg.finished_codes())
        where = f" AND LOWER(COALESCE(c.course, '')) NOT IN ({','.join('?' * len(hidden))})" if hidden else ""
        params: list = hidden
    else:
        where, params = f" AND LOWER(c.course) IN ({','.join('?' * len(codes))})", sorted(codes)
    book = "(c.path LIKE '%/Books/%' AND c.path NOT LIKE '%/Highlights/%')"  # his exported highlights are his notes
    if source == "book":
        where += f" AND {book}"
    elif source == "notes":
        where += f" AND NOT {book}"
    pool = max(50, limit * 6)
    ranks: dict[int, float] = {}
    with connect(path) as conn:
        fq = _fts_query(q)
        if fq:
            rows = conn.execute(
                f"SELECT c.id FROM chunks_fts f JOIN chunks c ON c.id = f.rowid WHERE chunks_fts MATCH ?{where} ORDER BY bm25(chunks_fts) LIMIT ?",
                [fq, *params, pool],
            ).fetchall()
            for i, r in enumerate(rows):
                ranks[r["id"]] = ranks.get(r["id"], 0) + 1 / (60 + i)
        qv = embed_query(q)
        if qv is not None:
            bad = conn.execute("UPDATE chunks SET vec = NULL WHERE vec IS NOT NULL AND length(vec) != ?", (DIM * 4,)).rowcount
            if bad:
                log.warning("%d search vectors had the wrong shape and will be made again", bad)
            rows = conn.execute(f"SELECT c.id, c.vec FROM chunks c WHERE c.vec IS NOT NULL{where}", params).fetchall()
            if rows:
                m = np.frombuffer(b"".join(r["vec"] for r in rows), dtype=np.float32).reshape(len(rows), DIM)
                top = np.argsort(-(m @ qv))[:pool]
                for i, j in enumerate(top):
                    cid = rows[int(j)]["id"]
                    ranks[cid] = ranks.get(cid, 0) + 1 / (60 + i)
        best = sorted(ranks, key=ranks.get, reverse=True)[:limit]
        if not best:
            return []
        found = {r["id"]: r for r in conn.execute(
            f"SELECT id, path, course, title, heading, text FROM chunks WHERE id IN ({','.join('?' * len(best))})", best)}
    return [{"path": found[i]["path"], "course": found[i]["course"], "title": found[i]["title"], "heading": found[i]["heading"],
             "text": found[i]["text"]} for i in best if i in found]


def scope(cfg: Config, course: str | None) -> set[str] | None:
    """Lowercased course codes a search covers, or None for "every active course"."""
    if not course:
        return None
    c = cfg.resolve(course)
    if c is None:
        return {course.lower()}
    return {c.code.lower(), *(r.lower() for r in c.related)}


def status(path: Path | None = None) -> dict[str, int]:
    p = path or index_path()
    if not p.exists():
        return {"notes": 0, "sections": 0, "without_meaning": 0}
    with connect(p) as conn:
        return {
            "notes": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "sections": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "without_meaning": conn.execute("SELECT COUNT(*) FROM chunks WHERE vec IS NULL").fetchone()[0],
        }
