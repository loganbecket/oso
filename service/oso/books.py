"""Textbooks as page-cited sources in the vault.

Anything in a course's `Books` folder is a book:

- a digital book is one file, `Books/<title>.pdf` or `Books/<title>.epub`
- a scanned book is a folder of scans or photos, `Books/<title>/Scans/`, read in file-name order; scans
  added later join the same book

Each book becomes `Books/<title>/`, holding `Book.md` (title, author, chapters with page ranges, the
syllabus readings that assign them, and pages read poorly) and one note per chapter. Inside a chapter
note every printed page starts with a `## p. 131` heading, so a search hit carries its page and Claude
can cite "ch. 4, p. 131".

Text comes from the file itself for digital books, and from the operating system's own text recognition
for scans (ocr.py), so bulk reading costs no Claude usage. Pages recognized poorly (mostly equations or
figures) are flagged and read by Claude from the page image in the background (reader.py), or on the
spot when he asks about one (`book_page`, `save_page_reading`); a reading is saved so it is never paid for twice.

Work is resumable and lives in the book's folder (`.oso-pages.json`), not the database, so a big book is
read a batch of pages per check and `oso fresh-start` does not throw away a finished book.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import notes, vault
from .config import Config

log = logging.getLogger("oso.books")

DIGITAL = {".pdf", ".epub"}
IMAGES = {".png", ".jpg", ".jpeg"}
STATE = ".oso-pages.json"
BUDGET_SECONDS = 90  # per check, across all books
CHUNK_PAGES = 20     # chapter size when a book has no table of contents or chapter headings
_CHAPTER_LINE = re.compile(r"^\s*(chapter|unit|part)\s+(\d+|[ivxlc]+)\b[.:\s-]*(.*)$", re.IGNORECASE)


# ---- finding books ------------------------------------------------------------------------------------


def book_roots(cfg: Config) -> list[tuple[Path, str]]:
    return [(cfg.vault / "Courses" / c.folder / "Books", c.code) for c in cfg.courses]


def sources(cfg: Config) -> list[dict]:
    """Every book: its output folder, its course, its kind, and its source files."""
    out = []
    for root, course in book_roots(cfg):
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in DIGITAL:
                out.append({"folder": root / p.stem, "course": course, "kind": p.suffix.lower()[1:], "files": [p]})
            elif p.is_dir() and (p / "Scans").is_dir():
                scans = sorted(f for f in (p / "Scans").iterdir() if f.is_file() and f.suffix.lower() in IMAGES | {".pdf"})
                if scans:
                    out.append({"folder": p, "course": course, "kind": "scan", "files": scans})
    return out


def _stamp(files: list[Path]) -> dict[str, dict]:
    return {f.name: {"size": f.stat().st_size, "mtime": round(f.stat().st_mtime, 3)} for f in files}


def _hash(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _unchanged(old: dict, stamp: dict, files: list[Path]) -> bool:
    """Same files by size and content. A new timestamp alone (Google Drive, a backup restore) is not a change,
    so the pages Claude already read are not paid for twice. Fills the content hashes into `stamp`."""
    if set(old) != set(stamp):
        return False
    for f in files:
        o, n = old[f.name], stamp[f.name]
        if not isinstance(o, dict):  # a stamp from before 0.18.1 held only the timestamp
            if round(float(o), 3) != n["mtime"]:
                return False
            n["hash"] = _hash(f)
            continue
        if o.get("size") != n["size"]:
            return False
        if o.get("mtime") == n["mtime"] and o.get("hash"):
            n["hash"] = o["hash"]
            continue
        n["hash"] = _hash(f)
        if o.get("hash") and n["hash"] != o["hash"]:
            return False
    return True


def _restore_readings(state: dict) -> None:
    """Give pages back the readings Claude made of the earlier copy of the book, matched by page label, as long
    as the book still has the same number of pages."""
    readings = state.get("readings")
    if not readings:
        return
    if state.get("total") is not None and state["total"] != state.get("readings_total"):
        state.pop("readings", None)
        state.pop("readings_total", None)
        return
    for p in state.get("pages", []):
        if not p.get("claude_text") and p["label"] in readings:
            p["claude_text"] = readings[p["label"]]
    if state.get("total") is not None and state["done"] >= state["total"]:
        state.pop("readings", None)
        state.pop("readings_total", None)


def load_state(folder: Path) -> dict:
    try:
        return json.loads((folder / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(folder: Path, state: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (STATE + ".part")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / STATE)


# ---- reading pages ------------------------------------------------------------------------------------


def _pdf_pages(path: Path, start: int, deadline: float) -> tuple[list[dict], int, dict]:
    """Text of each page from `start`, until the deadline. Returns pages, total page count, and metadata."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    total = len(doc)
    meta = {}
    try:
        m = doc.get_metadata_dict()
        meta = {"title": (m.get("Title") or "").strip(), "author": (m.get("Author") or "").strip()}
    except Exception:  # noqa: BLE001
        pass
    pages = []
    for i in range(start, total):
        if time.monotonic() > deadline:
            break
        tp = doc[i].get_textpage()
        text = tp.get_text_range() or ""
        try:
            label = doc.get_page_label(i) or str(i + 1)
        except Exception:  # noqa: BLE001
            label = str(i + 1)
        pages.append({"index": i, "label": label, "text": _clean(text), "file": path.name})
    doc.close()  # Windows keeps an open file locked
    return pages, total, meta


def _pdf_toc(path: Path) -> list[dict]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    out = []
    try:
        for item in doc.get_toc():
            if hasattr(item, "get_title"):  # pypdfium2 5
                dest = item.get_dest()
                index = dest.get_index() if dest is not None else None
                title = item.get_title()
            else:  # pypdfium2 4
                index, title = item.page_index, item.title
            if index is not None:
                out.append({"level": item.level, "title": (title or "").strip(), "index": index})
    except Exception:  # noqa: BLE001
        return []
    finally:
        doc.close()
    return out


def _scan_pages(cfg: Config, book: dict, start: int, deadline: float) -> tuple[list[dict], int]:
    """Recognize scanned pages from `start`: each image is a page; each page of a PDF scan is a page."""
    from . import ocr

    pages_dir = book["folder"] / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    plan: list[tuple[Path, int | None]] = []
    for f in book["files"]:
        if f.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(str(f))
            plan += [(f, i) for i in range(len(doc))]
            doc.close()
        else:
            plan.append((f, None))
    out = []
    idx = start
    while idx < len(plan) and time.monotonic() <= deadline:
        batch = []
        for idx in range(idx, min(idx + 8, len(plan))):  # recognized eight pages at a time
            f, i = plan[idx]
            image = pages_dir / f"p{idx + 1:04d}.png"
            if i is None:
                from PIL import Image

                with Image.open(f) as im:
                    im.convert("RGB").save(image)
            else:
                import pypdfium2 as pdfium

                doc = pdfium.PdfDocument(str(f))
                page = doc[i]
                page.render(scale=max(1.0, min(4.0, 1800 / (page.get_height() or 1)))).to_pil().save(image)
                doc.close()
            batch.append((idx, f, image))
        idx += 1
        for (n, f, image), raw in zip(batch, ocr.read_images([b[2] for b in batch])):
            text = _clean(raw)
            out.append({"index": n, "label": _printed_number(text) or str(n + 1), "text": text, "file": f.name,
                        "image": image.relative_to(cfg.vault).as_posix(), "poor": ocr.poor(text)})
    return out, len(plan)


def _printed_number(text: str) -> str | None:
    """A page number printed alone on the first or last line of a scanned page."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    for ln in (lines[:1] + lines[-1:]) if lines else []:
        if re.fullmatch(r"\d{1,4}", ln):
            return ln
    return None


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # words split across lines
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---- EPUB ------------------------------------------------------------------------------------------------


def _epub(path: Path) -> dict:
    """Chapters of an EPUB, in reading order, with printed page numbers where the book marks them."""
    z = zipfile.ZipFile(path)
    container = z.read("META-INF/container.xml").decode("utf-8", "replace")
    opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
    opf = z.read(opf_path).decode("utf-8", "replace")
    base = PurePosixPath(opf_path).parent
    manifest = {m.group("id"): m.group("href") for m in re.finditer(r'<item\b[^>]*\bid="(?P<id>[^"]+)"[^>]*\bhref="(?P<href>[^"]+)"', opf)}
    manifest.update({m.group("id"): m.group("href") for m in re.finditer(r'<item\b[^>]*\bhref="(?P<href>[^"]+)"[^>]*\bid="(?P<id>[^"]+)"', opf)})
    spine = [manifest[i] for i in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf) if i in manifest]
    title = _tag(opf, "dc:title") or path.stem
    author = _tag(opf, "dc:creator") or ""
    names = {}
    nav = next((href for href in manifest.values() if re.search(r"nav\.x?html?$|toc\.x?html?$", href)), None)
    toc_text = ""
    if nav:
        toc_text = z.read(str(base / nav)).decode("utf-8", "replace")
    else:
        ncx = next((href for href in manifest.values() if href.endswith(".ncx")), None)
        if ncx:
            toc_text = z.read(str(base / ncx)).decode("utf-8", "replace")
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)[^"]*"[^>]*>(.*?)</a>', toc_text, re.S):
        names.setdefault(PurePosixPath(m.group(1)).name, _strip(m.group(2)))
    for m in re.finditer(r'<navLabel>\s*<text>(.*?)</text>\s*</navLabel>\s*<content src="([^"#]+)', toc_text, re.S):
        names.setdefault(PurePosixPath(m.group(2)).name, _strip(m.group(1)))
    chapters = []
    for href in spine:
        raw = z.read(str(base / href)).decode("utf-8", "replace")
        name = names.get(PurePosixPath(href).name)
        if name is None and not chapters:
            continue  # cover and front matter before the first table-of-contents entry
        body, pages = _epub_body(raw)
        if not body.strip():
            continue
        if name is None:
            chapters[-1]["body"] += "\n\n" + body
            chapters[-1]["pages"] += pages
        else:
            chapters.append({"title": name, "body": body, "pages": pages})
    return {"title": title, "author": author, "chapters": chapters}


def _epub_body(raw: str) -> tuple[str, list[str]]:
    body = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", raw)
    pages: list[str] = []

    def pagebreak(m: re.Match) -> str:
        tag = m.group(0)
        num = re.search(r'(?:title|aria-label)="(?:page\s*)?([^"]+)"', tag) or re.search(r'id="(?:page|pg)[_-]?([^"]+)"', tag)
        if not num:
            return ""
        pages.append(num.group(1).strip())
        return f"\n\n## p. {num.group(1).strip()}\n\n"

    body = re.sub(r'<[^>]+epub:type="pagebreak"[^>]*/?>|<[^>]+role="doc-pagebreak"[^>]*/?>', pagebreak, body)
    body = re.sub(r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>", lambda m: f"\n\n### {_strip(m.group(1))}\n\n", body)
    return _strip(body, keep_lines=True), pages


def _tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", xml, re.S)
    return _strip(m.group(1)) if m else None


def _strip(fragment: str, keep_lines: bool = False) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</tr>", "\n", fragment) if keep_lines else fragment
    text = html.unescape(re.sub(r"<[^>]+>", "" if keep_lines else " ", text))
    if keep_lines:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(ln.strip() for ln in text.splitlines())).strip()
    return re.sub(r"\s+", " ", text).strip()


# ---- chapters ------------------------------------------------------------------------------------------


def chapters_from_pages(pages: list[dict], toc: list[dict]) -> list[dict]:
    """Group pages into chapters: by the table of contents (top level), else by "Chapter N" headings at the
    top of pages, else in runs of CHUNK_PAGES."""
    if not pages:
        return []
    top = [t for t in toc if t["level"] == min(x["level"] for x in toc)] if toc else []
    starts: list[tuple[int, str]] = []
    if len(top) >= 2:
        starts = [(t["index"], t["title"]) for t in top]
    else:
        for p in pages:
            for ln in [ln for ln in p["text"].splitlines() if ln.strip()][:3]:
                m = _CHAPTER_LINE.match(ln)
                if m:
                    starts.append((p["index"], f"{m.group(1).title()} {m.group(2)}" + (f": {m.group(3).strip()}" if m.group(3).strip() else "")))
                    break
    if not starts:
        return [{"title": f"Pages {group[0]['label']}–{group[-1]['label']}", "pages": group}
                for group in (pages[i:i + CHUNK_PAGES] for i in range(0, len(pages), CHUNK_PAGES))]
    starts.sort()
    out = []
    if starts[0][0] > pages[0]["index"]:
        starts.insert(0, (pages[0]["index"], "Front matter"))
    for n, (begin, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else float("inf")
        group = [p for p in pages if begin <= p["index"] < end]
        if group:
            out.append({"title": title, "pages": group})
    return out


def _edition(*texts: str) -> str | None:
    for t in texts:
        m = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+(?:ed\.?|edition)\b", t or "", re.IGNORECASE)
        if m:
            return f"{m.group(1)}{'st' if m.group(1).endswith('1') and m.group(1) != '11' else 'nd' if m.group(1).endswith('2') and m.group(1) != '12' else 'rd' if m.group(1).endswith('3') and m.group(1) != '13' else 'th'} edition"
    return None


# ---- writing the notes ----------------------------------------------------------------------------------


def _note_name(n: int, title: str) -> str:
    return f"{n:02d} {notes.safe_name(title)[:80]}.md"


def _is_chapter_note(path: Path) -> bool:
    """True for a chapter note Oso wrote and the student has not touched. His own file, a scraped page, or a
    chapter note he rewrote is never touched."""
    return vault.is_ours(path, vault.textbook_note)


def render(cfg: Config, book: dict, state: dict, conn=None) -> list[Path]:
    """Write the chapter notes and Book.md from the state. Returns the notes written."""
    folder: Path = book["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    title = state.get("title") or folder.name
    author = state.get("author") or ""
    edition = state.get("edition")
    course = book["course"]
    for old in folder.glob("[0-9][0-9] *.md"):
        if _is_chapter_note(old):
            old.unlink()  # Oso's chapter notes are regenerated as a set; anything the student put here stays
    written, index = [], []
    if state.get("kind") == "epub":
        chapters = [{"title": c["title"], "body": c["body"], "labels": c["pages"]} for c in state.get("chapters", [])]
    else:
        chapters = chapters_from_pages(state.get("pages", []), state.get("toc", []))
    poor_pages = []
    for n, ch in enumerate(chapters, start=1):
        if "body" in ch:
            labels = ch["labels"]
            body = ch["body"]
        else:
            labels = [p["label"] for p in ch["pages"]]
            parts = []
            for p in ch["pages"]:
                text = p.get("claude_text") or p["text"] or "(No text on this page.)"
                parts.append(f"## p. {p['label']}\n\n{text}")
                if p.get("poor") and not p.get("claude_text"):
                    poor_pages.append(p["label"])
                    if p.get("image"):
                        parts.append(f"> This page is mostly equations, tables, or figures. Claude is reading it from the page "
                                     f"image in the background; until then, the text above is rough.\n> ![[{p['image']}]]")
            body = "\n\n".join(parts)
        pages = f"{labels[0]}–{labels[-1]}" if len(labels) > 1 else (labels[0] if labels else None)
        fm = {"type": "textbook", "course": course, "book": title, "author": author or None, "edition": edition,
              "chapter": ch["title"], "pages": pages}
        path = folder / _note_name(n, ch["title"])
        if not vault.write_note(path, fm, f"# {ch['title']}\n\n{body}\n", vault.textbook_note):
            index.append((ch["title"], pages, path.stem))  # the student made this one his own; leave it as it is
            continue
        written.append(path)
        index.append((ch["title"], pages, path.stem))
    _write_index(cfg, book, state, index, poor_pages, conn)
    return written


def _write_index(cfg: Config, book: dict, state: dict, index: list, poor_pages: list[str], conn) -> None:
    folder: Path = book["folder"]
    done, total = state.get("done", 0), state.get("total") or 0
    lines = [f"# {state.get('title') or folder.name}", ""]
    if state.get("author"):
        lines.append(f"By {state['author']}" + (f", {state['edition']}" if state.get("edition") else "") + ".")
        lines.append("")
    if total and done < total:
        lines += [f"Oso is still reading this book: {done} of {total} pages so far. It continues on each check.", ""]
    lines += ["## Chapters", "", "| Chapter | Pages |", "| --- | --- |"]
    for title, pages, stem in index:
        lines.append(f"| [[{stem}\\|{title}]] | {pages or ''} |")
    lines.append("")
    readings = assigned_readings(conn, book["course"]) if conn is not None else []
    if readings:
        lines += ["## Assigned in the syllabus", ""] + [f"- {r}" for r in readings] + [""]
    if poor_pages:
        lines += ["## Pages waiting for Claude", "",
                  "These are mostly equations, tables, or figures; Claude is reading them from their images in the background: "
                  + ", ".join(f"p. {p}" for p in poor_pages) + ".", ""]
    fm = {"type": "book", "course": book["course"], "title": state.get("title"), "author": state.get("author") or None,
          "edition": state.get("edition"), "source": ", ".join(f.name for f in book["files"]) if book["kind"] != "scan" else "Scans/",
          "pages": total or None}
    vault.write_note(folder / "Book.md", fm, "\n".join(lines), vault.book_index)


def assigned_readings(conn, course: str) -> list[str]:
    """Reading items for the course (from the syllabus or Canvas), as dated lines."""
    try:
        rows = conn.execute(
            """SELECT COALESCE(user_title, title) AS title, COALESCE(user_due_at, due_at) AS due FROM items
               WHERE deleted_at IS NULL AND merged_into IS NULL AND kind = 'reading'
               AND COALESCE(user_course, course_code) = ? ORDER BY due""",
            (course,),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [f"{(r['due'] or '')[:10]}: {r['title']}".lstrip(": ") for r in rows]


# ---- the work per check ---------------------------------------------------------------------------------


def process(cfg: Config, conn=None, budget: float = BUDGET_SECONDS) -> dict[str, int]:
    """Read new or changed books, a batch of pages at a time within the time budget."""
    deadline = time.monotonic() + budget
    counts = {"books": 0, "pages": 0, "finished": 0}
    for book in sources(cfg):
        if time.monotonic() > deadline:
            break
        folder: Path = book["folder"]
        state = load_state(folder)
        stamp = _stamp(book["files"])
        old = state.get("sources") or {}
        if old and _unchanged(old, stamp, book["files"]):
            if old != stamp:
                state["sources"] = stamp
                save_state(folder, state)
        else:
            kept: list[dict] = []
            if (book["kind"] == "scan" and old and all(_unchanged({k: v}, {k: stamp[k]}, [f]) for k, v in old.items()
                                                       for f in book["files"] if f.name == k and k in stamp)
                    and min(k for k in stamp if k not in old) > max(old)):
                kept = state.get("pages", [])  # new scans sort after the old ones: they join the end of the book
            readings = {} if kept else {p["label"]: p["claude_text"] for p in state.get("pages", []) if p.get("claude_text")}
            for f in book["files"]:
                stamp[f.name].setdefault("hash", _hash(f))
            state = {**({k: state[k] for k in ("title",) if k in state} if kept else {}),
                     "kind": book["kind"], "sources": stamp, "done": len(kept), "total": None, "pages": kept, "toc": [],
                     **({"readings": readings, "readings_total": state.get("total")} if readings else {})}
        if state.get("total") is not None and state["done"] >= state["total"]:
            continue
        counts["books"] += 1
        try:
            if book["kind"] == "epub":
                info = _epub(book["files"][0])
                labels = [lab for c in info["chapters"] for lab in c["pages"]]
                state.update(title=info["title"], author=info["author"], chapters=info["chapters"],
                             edition=_edition(info["title"]), total=len(info["chapters"]), done=len(info["chapters"]))
                counts["pages"] += len(labels)
            elif book["kind"] == "pdf":
                pages, total, meta = _pdf_pages(book["files"][0], state["done"], deadline)
                if state["done"] == 0:
                    state["toc"] = _pdf_toc(book["files"][0])
                    state["title"] = meta.get("title") or book["files"][0].stem
                    state["author"] = meta.get("author") or ""
                    state["edition"] = _edition(state["title"], book["files"][0].stem)
                state["pages"] += pages
                state.update(total=total, done=state["done"] + len(pages))
                _restore_readings(state)
                counts["pages"] += len(pages)
            else:
                pages, total = _scan_pages(cfg, book, state["done"], deadline)
                state.setdefault("title", folder.name)
                state["pages"] += pages
                state.update(total=total, done=state["done"] + len(pages))
                _restore_readings(state)
                counts["pages"] += len(pages)
        except Exception as e:  # noqa: BLE001
            log.warning("could not read book %s: %s", folder.name, type(e).__name__)
            state["error"] = f"Could not read this book ({type(e).__name__})."
            save_state(folder, state)
            continue
        state.pop("error", None)
        try:
            render(cfg, book, state, conn)
        except Exception as e:  # noqa: BLE001  the pages are read; the notes get another try next check
            log.warning("could not write the notes for %s: %s", folder.name, type(e).__name__)
            state["error"] = f"Could not write this book's notes ({type(e).__name__})."
            state["done"] = max(0, state["done"] - 1) if state.get("total") and state["done"] >= state["total"] else state["done"]
            save_state(folder, state)
            continue
        save_state(folder, state)
        if state["done"] >= (state["total"] or 0):
            counts["finished"] += 1
    return counts


def progress(cfg: Config) -> list[dict]:
    out = []
    for book in sources(cfg):
        s = load_state(book["folder"])
        out.append({"book": s.get("title") or book["folder"].name, "course": book["course"], "folder": book["folder"],
                    "done": s.get("done", 0), "total": s.get("total"), "error": s.get("error"),
                    "poor": sum(1 for p in s.get("pages", []) if p.get("poor") and not p.get("claude_text"))})
    return out


def reprocess(cfg: Config, title: str) -> str:
    for book in sources(cfg):
        s = load_state(book["folder"])
        if title.lower() in ((s.get("title") or "").lower(), book["folder"].name.lower()):
            (book["folder"] / STATE).unlink(missing_ok=True)
            return f"{s.get('title') or book['folder'].name} will be read again from the start on the next check."
    return f"No book called {title!r}."


# ---- a page, for Claude --------------------------------------------------------------------------------


def _find(cfg: Config, book: str) -> dict | None:
    want = book.strip().lower()
    for b in sources(cfg):
        s = load_state(b["folder"])
        if want in ((s.get("title") or "").lower(), b["folder"].name.lower()) or want in (s.get("title") or "").lower():
            return b
    return None


def page(cfg: Config, book: str, label: str) -> dict:
    """One page: its text, whether it was read poorly, and a page image Claude can look at (rendered on
    demand for digital books)."""
    b = _find(cfg, book)
    if b is None:
        raise ValueError(f"No book called {book!r}.")
    s = load_state(b["folder"])
    p = next((x for x in s.get("pages", []) if x["label"] == str(label)), None)
    if p is None:
        raise ValueError(f"{s.get('title') or book} has no page {label} (yet).")
    image = p.get("image")
    if not image and b["kind"] == "pdf":
        import pypdfium2 as pdfium

        out = b["folder"] / "pages" / f"p{p['index'] + 1:04d}.png"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            doc = pdfium.PdfDocument(str(b["files"][0]))
            pg = doc[p["index"]]
            pg.render(scale=max(1.0, min(4.0, 1800 / (pg.get_height() or 1)))).to_pil().save(out)
            doc.close()
        image = out.relative_to(cfg.vault).as_posix()
    return {"book": s.get("title"), "page": p["label"], "text": p.get("claude_text") or p["text"],
            "read_poorly": bool(p.get("poor") and not p.get("claude_text")),
            "image": image, "image_full_path": str(cfg.vault / image) if image else None}


def save_page_reading(cfg: Config, book: str, label: str, text: str, conn=None) -> str:
    b = _find(cfg, book)
    if b is None:
        raise ValueError(f"No book called {book!r}.")
    s = load_state(b["folder"])
    p = next((x for x in s.get("pages", []) if x["label"] == str(label)), None)
    if p is None:
        raise ValueError(f"{s.get('title') or book} has no page {label}.")
    p["claude_text"] = text.strip()
    save_state(b["folder"], s)
    render(cfg, b, s, conn)
    return f"Saved the reading of p. {label}; it won't need reading again."
