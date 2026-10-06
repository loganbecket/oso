"""Turn course files into Markdown beside the original, so Claude can read and search them.

The Markdown file has the same name with `.md` appended (`Lecture 3.pptx` gets `Lecture 3.pptx.md`) and is
rewritten only when the original is newer.

- Microsoft Office, PDF, CSV, HTML, EPUB: Microsoft's MarkItDown.
- LibreOffice (.odt, .ods, .odp) and older Office formats (.doc, .xls, .ppt, .rtf): LibreOffice itself, run
  headless, turns them into the modern Office format, then MarkItDown reads that. Without LibreOffice
  installed, OpenDocument files still get a plain-text reading from a small built-in reader.
- Google Docs, Sheets, and Slides: Google Drive for Desktop keeps only a pointer to them, not their content,
  and reading the content would need a broad Google permission. They get a short note with the link, which
  Claude follows through its Google Drive connector.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from . import notes
from .config import Config

log = logging.getLogger("oso.convert")

MARKITDOWN = {".docx", ".pptx", ".xlsx", ".xls", ".pdf", ".csv", ".html", ".htm", ".epub"}
OPENDOCUMENT = {".odt", ".ods", ".odp"}
LEGACY = {".doc", ".ppt", ".rtf"}
GOOGLE = {".gdoc": "document", ".gsheet": "spreadsheets", ".gslides": "presentation"}
CONVERTIBLE = MARKITDOWN | OPENDOCUMENT | LEGACY | set(GOOGLE)

_LO_TARGET = {".odt": "docx", ".doc": "docx", ".rtf": "docx", ".ods": "xlsx", ".odp": "pptx", ".ppt": "pptx"}
SKIP_FOLDERS = {"Handwriting", "Quizzes", "pages", ".obsidian", ".trash"}


def convert_vault(cfg: Config) -> list[Path]:
    """Convert anything new or changed under Courses/ and Clippings/. Returns the Markdown files written."""
    written: list[Path] = []
    for root in (cfg.vault / "Courses", cfg.vault / "Clippings"):
        if not root.exists():
            continue
        for src in root.rglob("*"):
            if not src.is_file() or src.suffix.lower() not in CONVERTIBLE:
                continue
            if SKIP_FOLDERS & set(src.relative_to(cfg.vault).parts):
                continue
            out = src.with_name(src.name + ".md")
            if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
                continue
            try:
                body = to_markdown(src)
            except Exception as e:  # noqa: BLE001
                log.warning("could not convert %s: %s", src.name, type(e).__name__)
                continue
            fm = {
                "type": "google-file" if src.suffix.lower() in GOOGLE else notes.guess_type(src.stem),
                "course": _course_from_path(cfg, src),
                "source": src.name,
                "converted": notes.stamp(),
            }
            out.write_text(notes.with_front_matter(fm, f"# {src.stem}\n\n{body.strip()}\n"), encoding="utf-8")
            written.append(out)
    return written


def to_markdown(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in GOOGLE:
        return _google_pointer(path)
    if ext in MARKITDOWN:
        return _markitdown(path)
    if ext in OPENDOCUMENT or ext in LEGACY:
        converted = _via_libreoffice(path)
        if converted is not None:
            return converted
        if ext in OPENDOCUMENT:
            return _odf_text(path)
        raise RuntimeError("LibreOffice is needed to read this older file format")
    raise ValueError(f"unsupported file type {ext}")


def _markitdown(path: Path) -> str:
    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(str(path))
    text = (getattr(result, "markdown", None) or result.text_content or "").strip()
    if not text and path.suffix.lower() == ".pdf":
        return "(No text layer found. If this is a scan or handwriting, move it to the course's Handwriting folder to have it transcribed.)"
    return text


def libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        exe = shutil.which(name)
        if exe:
            return exe
    for candidate in (
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _via_libreoffice(path: Path) -> str | None:
    exe = libreoffice()
    if not exe:
        return None
    target = _LO_TARGET[path.suffix.lower()]
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        try:
            subprocess.run(
                [exe, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", target, "--outdir", tmp, str(path)],
                capture_output=True, timeout=180, check=True,
            )
        except (subprocess.SubprocessError, OSError) as e:
            log.warning("LibreOffice could not convert %s: %s", path.name, type(e).__name__)
            return None
        out = Path(tmp) / f"{path.stem}.{target}"
        if not out.exists():
            return None
        return _markitdown(out)


_ODF_NS = {
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
}


def _odf_text(path: Path) -> str:
    """Plain reading of an OpenDocument file when LibreOffice is not installed: headings, paragraphs, tables, slides."""
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("content.xml"))
    t = "{%s}" % _ODF_NS["text"]
    tb = "{%s}" % _ODF_NS["table"]
    dr = "{%s}" % _ODF_NS["draw"]
    out: list[str] = []

    def text_of(el) -> str:
        return "".join(el.itertext()).strip()

    def walk(el):
        for child in el:
            tag = child.tag
            if tag == t + "h":
                level = int(child.get(t + "outline-level", "1"))
                if text_of(child):
                    out.append(f"{'#' * min(level + 1, 6)} {text_of(child)}\n")
            elif tag == t + "p":
                if text_of(child):
                    out.append(text_of(child) + "\n")
            elif tag == t + "list-item":
                if text_of(child):
                    out.append(f"- {text_of(child)}")
            elif tag == tb + "table":
                rows = []
                for row in child.iter(tb + "table-row"):
                    cells = [text_of(c) for c in row if c.tag == tb + "table-cell"]
                    if any(cells):
                        rows.append(cells)
                if rows:
                    out.append(f"## Sheet: {child.get(tb + 'name', '')}" if path.suffix.lower() == ".ods" else "")
                    out.append(_table(rows) + "\n")
            elif tag == dr + "page":
                out.append(f"## Slide: {child.get(dr + 'name', '')}")
                walk(child)
            else:
                walk(child)

    walk(root)
    return "\n".join(line for line in out if line is not None)


def _google_pointer(path: Path) -> str:
    kind = GOOGLE[path.suffix.lower()]
    url = None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        url = data.get("url") or (f"https://docs.google.com/{kind}/d/{data['doc_id']}" if data.get("doc_id") else None)
    except (ValueError, OSError):
        pass
    label = {"document": "Google Doc", "spreadsheets": "Google Sheet", "presentation": "Google Slides file"}[kind]
    lines = [
        f"This is a {label}. Its content lives in Google Drive, not on this computer, so it is not in this note.",
        "Claude: read it through the Google Drive connector.",
    ]
    if url:
        lines.append(f"\nLink: {url}")
    return "\n".join(lines)


def _table(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    esc = lambda c: c.replace("|", "\\|").replace("\n", " ")  # noqa: E731
    head = "| " + " | ".join(esc(c) for c in rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join([head, sep, *body])


def _course_from_path(cfg: Config, path: Path) -> str | None:
    try:
        rel = path.relative_to(cfg.vault / "Courses")
    except ValueError:
        return None
    low = rel.as_posix().lower() + "/"
    for c in sorted(cfg.courses, key=lambda c: len(c.folder), reverse=True):
        if low.startswith(c.folder.lower().rstrip("/") + "/"):
            return c.code
    return None
