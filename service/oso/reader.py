"""Hard pages read automatically, in the background, within a daily limit.

Printed text that the computer's own text recognition reads cleanly never reaches Claude. Everything else
does, without the student asking: handwritten pages (his notes, from the tablet or scans), and pages of
books and scanned handouts that recognition read poorly because they are mostly equations, tables,
diagrams, or drawings. On each check, Oso has Claude Code on the laptop read a few of them, one page per
call, and puts the reading in place of the poor text, with the page image still linked.

Pages are read most urgent first: his handwritten notes, then pages from courses with the nearest exam, then
the rest. There is no limit by default; `auto_read_per_day` (settings) can cap pages per day, since his
Claude plan has usage limits. Each check stops starting new pages after CHECK_MINUTES, so it stays inside
the time Windows allows a background check; what is left continues on the next check.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import books, handwriting
from .config import Config
from .db import EFFECTIVE

log = logging.getLogger("oso.reader")

META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"
CHECK_MINUTES = 7
# A scanned handout's poor page, as convert.py writes it: replaced in place once read.
HANDOUT_BLOCK = re.compile(r'<!-- oso:needs-reading image="(?P<image>[^"]+)" -->\n(?P<text>.*?)\n<!-- oso:end -->', re.S)

PROMPT = """Read the page image at {image} with the Read tool. It is page {page} of {what}, for {course}.

Write out the page as Markdown, faithfully and completely:
- printed and handwritten text word for word, in reading order, with headings and lists as they appear
- every equation in LaTeX: $...$ inline, $$...$$ on its own line
- every table as a Markdown table
- every diagram, graph, figure, or drawing as a blockquote starting "> Figure:" that says what it shows,
  including labels, axes, and values written on it
- anything unreadable as [?]; never guess

Output only the page's content. Do not add commentary, a summary, or a page heading."""


def _claude() -> str | None:
    return shutil.which("claude")


def read_page(exe: str, cfg: Config, image: Path, page: str, what: str, course: str) -> str:
    """One page through Claude Code. Raises subprocess.SubprocessError on failure."""
    result = subprocess.run(
        [exe, "-p", PROMPT.format(image=image, page=page, what=what, course=course), "--model", cfg.transcribe_model,
         "--output-format", "text", "--allowedTools", "Read", "--max-turns", "4"],
        cwd=str(cfg.vault), capture_output=True, text=True, timeout=300, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise subprocess.SubprocessError((result.stderr or result.stdout or "no output").strip()[:200])
    return result.stdout.strip()


# ---- what is waiting ------------------------------------------------------------------------------------


def _exam_rank(conn: sqlite3.Connection, cfg: Config, now: datetime) -> dict[str, int]:
    """Courses ordered by their next exam (sooner first); courses with none come last."""
    soon = (now + timedelta(days=60)).isoformat(timespec="minutes")
    rows = conn.execute(
        f"""SELECT course_code, MIN(due_at) AS next FROM (SELECT kind, {EFFECTIVE} FROM items
            WHERE deleted_at IS NULL AND merged_into IS NULL) WHERE kind = 'exam' AND due_at >= ? AND due_at <= ?
            GROUP BY course_code ORDER BY next""",
        (now.isoformat(timespec="minutes"), soon),
    ).fetchall()
    rank = {r["course_code"]: i for i, r in enumerate(rows)}
    return {c.code: rank.get(c.code, len(rank)) for c in cfg.courses}


def waiting(cfg: Config, conn: sqlite3.Connection, now: datetime) -> list[dict]:
    """Book and handout pages waiting for Claude, most urgent first (handwriting is counted separately)."""
    rank = _exam_rank(conn, cfg, now)
    jobs = []
    for b in books.sources(cfg):
        if not cfg.is_active(b["course"]):
            continue
        state = books.load_state(b["folder"])
        for p in state.get("pages", []):
            if p.get("poor") and not p.get("claude_text") and (p.get("image") or b["kind"] == "pdf"):
                jobs.append({"kind": "book", "course": b["course"], "book": state.get("title") or b["folder"].name,
                             "folder": b["folder"], "page": p["label"], "order": p["index"]})
    for c in cfg.courses:
        if c.finished:
            continue
        root = cfg.vault / "Courses" / c.folder
        if not root.is_dir():
            continue
        for md in root.rglob("*.md"):
            if "Books" in md.relative_to(root).parts:
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for n, m in enumerate(HANDOUT_BLOCK.finditer(text)):
                jobs.append({"kind": "handout", "course": c.code, "file": md, "image": m.group("image"), "order": n,
                             "mtime": md.stat().st_mtime})
    jobs.sort(key=lambda j: (rank.get(j["course"], 99), j["kind"] != "book", -j.get("mtime", 0) if j["kind"] == "handout" else 0,
                             str(j.get("folder") or j.get("file")), j["order"]))
    return jobs


def handwriting_waiting(conn: sqlite3.Connection) -> int:
    return len(handwriting.pending(conn, limit=100000))


# ---- the daily allowance ----------------------------------------------------------------------------------


def used_today(conn: sqlite3.Connection, now: datetime) -> int:
    from . import schema

    schema.apply(conn)
    row = conn.execute("SELECT value FROM meta WHERE key = 'auto_read'").fetchone()
    if not row:
        return 0
    day, _, n = row["value"].partition(" ")
    return int(n) if day == now.date().isoformat() else 0


def _add_used(conn: sqlite3.Connection, now: datetime, n: int) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('auto_read', ?)", (f"{now.date().isoformat()} {used_today(conn, now) + n}",))


# ---- the work per check -------------------------------------------------------------------------------------


def run(cfg: Config, conn: sqlite3.Connection, now: datetime) -> dict[str, int]:
    counts = {"read": 0, "failed": 0, "waiting": 0}
    if not cfg.auto_read:
        return counts
    exe = _claude()
    deadline = time.monotonic() + CHECK_MINUTES * 60
    limited = cfg.auto_read_per_day > 0
    allowance = max(0, cfg.auto_read_per_day - used_today(conn, now)) if limited else 10**9
    if exe and allowance > 0:
        # His own handwritten notes first, a few pages at a time so the time limit is checked between them.
        from . import transcribe

        try:
            while allowance > 0 and time.monotonic() < deadline and handwriting_waiting(conn):
                t = transcribe.run(conn, cfg, limit=min(allowance, 3))
                done = t["pages"] + t["failed"]
                counts["read"] += t["pages"]
                counts["failed"] += t["failed"]
                _add_used(conn, now, done)
                allowance -= done
                if done == 0:
                    break
        except transcribe.ClaudeMissing:
            pass
        for job in waiting(cfg, conn, now)[:max(0, allowance)]:
            if time.monotonic() >= deadline:
                break
            try:
                _do(exe, cfg, conn, job)
                counts["read"] += 1
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                log.warning("could not read a page: %s", type(e).__name__)
                counts["failed"] += 1
            _add_used(conn, now, 1)
            conn.commit()
    counts["waiting"] = len(waiting(cfg, conn, now)) + handwriting_waiting(conn)
    return counts


def _do(exe: str, cfg: Config, conn: sqlite3.Connection, job: dict) -> None:
    c = cfg.course_for(job["course"])
    course = c.name if c else job["course"]
    if job["kind"] == "book":
        p = books.page(cfg, job["book"], job["page"])
        text = read_page(exe, cfg, Path(p["image_full_path"]), job["page"], f'the textbook "{job["book"]}"', course)
        books.save_page_reading(cfg, job["book"], job["page"], text, conn)
        return
    image = cfg.vault / job["image"]
    text = read_page(exe, cfg, image, str(job["order"] + 1), f'the handout "{job["file"].stem}"', course)
    body = job["file"].read_text(encoding="utf-8")
    marker = f'<!-- oso:needs-reading image="{job["image"]}" -->'
    for m in HANDOUT_BLOCK.finditer(body):
        if m.group(0).startswith(marker):
            body = body[:m.start()] + f"{text}\n\n![[{job['image']}]]" + body[m.end():]
            break
    job["file"].write_text(body, encoding="utf-8")
