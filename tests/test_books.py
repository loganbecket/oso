import json
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from oso import books, config as cfgmod, filing, fresh, ocr, readiness, search
from oso.config import Config, Course

LOREM = "Velocity is the rate of change of position with respect to time and acceleration is the rate of change of velocity "


def make_pdf(path: Path, page_texts: list[str], toc: list[tuple[str, int]] | None = None, labels_from: int | None = None) -> None:
    """A real PDF with a text layer, built by hand, plus an outline and page labels added with pypdf."""
    objs = []
    kids = []
    font_id = 3
    for i, text in enumerate(page_texts):
        content = "BT /F1 11 Tf 40 760 Td 14 TL " + " ".join(f"({line}) '" for line in text.split("\n")) + " ET"
        cid = 4 + 2 * i
        pid = cid + 1
        objs.append((cid, f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"))
        objs.append((pid, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"))
        kids.append(f"{pid} 0 R")
    head = [(1, "<< /Type /Catalog /Pages 2 0 R >>"), (2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"),
            (3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")]
    out, offsets = b"%PDF-1.4\n", {}
    for num, body in head + objs:
        offsets[num] = len(out)
        out += f"{num} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    n = max(offsets) + 1
    out += f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for i in range(1, n):
        out += f"{offsets[i]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R /Info << /Title (Physics for Students, 3rd Edition) /Author (A. Author) >> >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    if toc or labels_from:
        from pypdf import PdfReader, PdfWriter
        from pypdf.constants import PageLabelStyle

        import io

        w = PdfWriter(clone_from=PdfReader(io.BytesIO(path.read_bytes())))  # not holding the file open (Windows)
        for title, idx in toc or []:
            w.add_outline_item(title, idx)
        if labels_from:
            w.set_page_label(0, len(page_texts) - 1, style=PageLabelStyle.DECIMAL, start=labels_from)
        w.add_metadata({"/Title": "Physics for Students, 3rd Edition", "/Author": "A. Author"})
        with path.open("wb") as f:
            w.write(f)


def make_epub(path: Path) -> None:
    chap = lambda title, body: f'<html xmlns:epub="http://www.idpf.org/2007/ops"><body><h1>{title}</h1>{body}</body></html>'  # noqa: E731
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", """<package><metadata><dc:title>Calculus Made Plain</dc:title><dc:creator>B. Writer</dc:creator></metadata>
            <manifest><item id="cover" href="cover.xhtml"/><item id="nav" href="nav.xhtml"/><item id="c1" href="c1.xhtml"/><item id="c2" href="c2.xhtml"/></manifest>
            <spine><itemref idref="cover"/><itemref idref="c1"/><itemref idref="c2"/></spine></package>""")
        z.writestr("OEBPS/nav.xhtml", '<nav><a href="c1.xhtml">1. Limits</a><a href="c2.xhtml#x">2. Derivatives</a></nav>')
        z.writestr("OEBPS/cover.xhtml", "<html><body><p>Cover</p></body></html>")
        z.writestr("OEBPS/c1.xhtml", chap("Limits", '<span epub:type="pagebreak" title="1"/><p>A limit describes approach.</p><span epub:type="pagebreak" title="2"/><p>More on limits.</p>'))
        z.writestr("OEBPS/c2.xhtml", chap("Derivatives", '<span epub:type="pagebreak" title="3"/><h2>Rules</h2><p>The derivative is a rate.</p>'))


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    (cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Books").mkdir(parents=True)
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path / "data")
    (tmp_path / "data").mkdir()
    return cfg


def books_dir(cfg):
    return cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Books"


def test_pdf_book_by_table_of_contents_with_printed_page_numbers(env):
    cfg = env
    pages = [f"Front page {i}" for i in range(2)] + [f"Chapter text {i}\n{LOREM}" for i in range(4)]
    make_pdf(books_dir(cfg) / "Physics.pdf", pages, toc=[("1 Motion", 2), ("2 Forces", 4)], labels_from=101)
    c = books.process(cfg)
    assert c == {"books": 1, "pages": 6, "finished": 1}
    folder = books_dir(cfg) / "Physics"
    names = sorted(p.name for p in folder.glob("[0-9]*.md"))
    assert names == ["01 Front matter.md", "02 1 Motion.md", "03 2 Forces.md"]
    motion = (folder / "02 1 Motion.md").read_text(encoding="utf-8")
    assert "type: textbook" in motion and "book: Physics for Students, 3rd Edition" in motion and "edition: 3rd edition" in motion
    assert "pages: 103–104" in motion and "## p. 103" in motion and "rate of change of position" in motion
    index = (folder / "Book.md").read_text(encoding="utf-8")
    assert "By A. Author, 3rd edition." in index and "| [[02 1 Motion\\|1 Motion]] | 103–104 |" in index
    assert books.process(cfg)["books"] == 0  # read once


def test_search_finds_book_pages_and_filters(env, tmp_path, monkeypatch):
    cfg = env
    make_pdf(books_dir(cfg) / "Physics.pdf", [f"Kinematics page\n{LOREM}", "Forces page about Newton and friction and normal forces acting on blocks"],
             toc=[("1 Motion", 0), ("2 Forces", 1)])
    books.process(cfg)
    notes_dir = cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes"
    notes_dir.mkdir()
    (notes_dir / "Day 1.md").write_text("# Friction\n\nMy notes say friction is about Newton.\n")
    monkeypatch.setattr(search, "embed_passages", lambda texts: None)
    monkeypatch.setattr(search, "embed_query", lambda text: None)
    db = tmp_path / "s.sqlite"
    search.update(cfg, db)
    hits = search.query(cfg, "friction Newton", path=db, source="book")
    assert hits and all("/Books/" in h["path"] for h in hits)
    assert hits[0]["heading"] == "p. 2" and hits[0]["title"] == "Physics for Students, 3rd Edition, 2 Forces"
    assert all("/Books/" not in h["path"] for h in search.query(cfg, "friction Newton", path=db, source="notes"))


def test_chapter_headings_and_chunks_without_a_toc(env):
    assert [c["title"] for c in books.chapters_from_pages(
        [{"index": i, "label": str(i + 1), "text": t} for i, t in enumerate(["Preface", "Chapter 1: Waves\ntext", "more", "CHAPTER 2 Sound\ntext"])], [])] == \
        ["Front matter", "Chapter 1: Waves", "Chapter 2: Sound"]
    plain = [{"index": i, "label": str(i + 1), "text": "words"} for i in range(45)]
    assert [c["title"] for c in books.chapters_from_pages(plain, [])] == ["Pages 1–20", "Pages 21–40", "Pages 41–45"]


def test_big_book_is_read_a_batch_at_a_time(env, monkeypatch):
    cfg = env
    make_pdf(books_dir(cfg) / "Big.pdf", [f"Page {i}\n{LOREM}" for i in range(6)])
    clock = iter(range(0, 1000))
    monkeypatch.setattr(books.time, "monotonic", lambda: next(clock))
    first = books.process(cfg, budget=4)
    assert 0 < first["pages"] < 6 and first["finished"] == 0
    assert "still reading this book" in (books_dir(cfg) / "Big" / "Book.md").read_text(encoding="utf-8")
    while books.process(cfg, budget=4)["finished"] == 0:
        pass
    state = books.load_state(books_dir(cfg) / "Big")
    assert state["done"] == state["total"] == 6 and [p["label"] for p in state["pages"]] == [str(i) for i in range(1, 7)]


def test_epub_chapters_and_page_marks(env):
    cfg = env
    make_epub(books_dir(cfg) / "Calc.epub")
    books.process(cfg)
    folder = books_dir(cfg) / "Calc"
    one = (folder / "01 1. Limits.md").read_text(encoding="utf-8")
    assert "book: Calculus Made Plain" in one and "pages: 1–2" in one and "## p. 2\n\nMore on limits." in one
    two = (folder / "02 2. Derivatives.md").read_text(encoding="utf-8")
    assert "### Rules" in two and "## p. 3" in two
    assert "Cover" not in one


def test_scans_recognized_join_later_and_poor_pages(env, monkeypatch):
    cfg = env
    texts = {"a.png": "12\n" + LOREM * 3, "b.png": "x = (a+b)/2 ; ∫ dx", "c.png": "14\n" + LOREM * 3}
    monkeypatch.setattr(ocr, "read_images", lambda ps: [texts[books_order[int(p.stem[1:]) - 1]] for p in ps])
    scans = books_dir(cfg) / "Mechanics" / "Scans"
    scans.mkdir(parents=True)
    books_order = ["a.png", "b.png"]
    for name in books_order:
        Image.new("RGB", (60, 80), "white").save(scans / name)
    books.process(cfg)
    state = books.load_state(books_dir(cfg) / "Mechanics")
    assert [p["label"] for p in state["pages"]] == ["12", "2"] and [p["poor"] for p in state["pages"]] == [False, True]
    assert "Pages read poorly" in (books_dir(cfg) / "Mechanics" / "Book.md").read_text(encoding="utf-8")
    # a later scan joins the end without re-reading the first ones
    books_order.append("c.png")
    Image.new("RGB", (60, 80), "white").save(scans / "c.png")
    assert books.process(cfg)["pages"] == 1
    assert [p["label"] for p in books.load_state(books_dir(cfg) / "Mechanics")["pages"]] == ["12", "2", "14"]
    # Claude reads the poor page once from its image, and that reading is kept
    pg = books.page(cfg, "Mechanics", "2")
    assert pg["read_poorly"] and pg["image"].endswith("p0002.png") and Path(pg["image_full_path"]).exists()
    books.save_page_reading(cfg, "mechanics", "2", "$x = \\frac{a+b}{2}$")
    assert not books.page(cfg, "Mechanics", "2")["read_poorly"]
    chapter = next((books_dir(cfg) / "Mechanics").glob("01 *.md")).read_text(encoding="utf-8")
    assert "\\frac{a+b}{2}" in chapter and "was read poorly" not in chapter


def test_digital_page_image_rendered_on_demand(env):
    cfg = env
    make_pdf(books_dir(cfg) / "Physics.pdf", [f"Only page\n{LOREM}"])
    books.process(cfg)
    pg = books.page(cfg, "Physics", "1")
    assert pg["image"].endswith("pages/p0001.png") and Path(pg["image_full_path"]).exists() and not pg["read_poorly"]


def test_clipped_book_page_files_into_the_book(env):
    cfg = env
    clips = cfg.vault / "Clippings"
    clips.mkdir()
    (clips / "Reader page.md").write_text("---\ncourse: Physics\nbook: Physics for Students\npage: '88'\n---\n\nSome text from the reader.\n")
    assert filing.file_clippings(cfg) == 1
    moved = books_dir(cfg) / "Physics for Students" / "Clipped" / "Reader page.md"
    text = moved.read_text(encoding="utf-8")
    assert "type: textbook" in text and "## p. 88\n\nSome text from the reader." in text


def test_fresh_start_keeps_books(env):
    cfg = env
    make_pdf(books_dir(cfg) / "Physics.pdf", ["x"])
    (cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes").mkdir()
    (cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes" / "n.md").write_text("x")
    (cfg.vault / "Today.md").write_text("x")
    gone = {p.relative_to(cfg.vault).as_posix() for p in fresh.plan(cfg)}
    assert gone == {"Today.md", "Courses/2026 Fall/Physics/Notes"}


def test_readiness_flags_assigned_chapters_without_notes(env):
    from oso import db, merge
    from oso.db import SCHEMA, Item

    cfg = env
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 11, 2, 8, 0, tzinfo=tz)
    items = [Item(source="syllabus", external_id="e1", course_code="PHYS-110", title="Exam 1", kind="exam", due_at=now - timedelta(days=30)),
             Item(source="syllabus", external_id="r1", course_code="PHYS-110", title="Read Ch. 3", kind="reading", due_at=now - timedelta(days=35)),
             Item(source="syllabus", external_id="r2", course_code="PHYS-110", title="Read chapters 4-5", kind="reading", due_at=now - timedelta(days=10)),
             Item(source="syllabus", external_id="e2", course_code="PHYS-110", title="Exam 2", kind="exam", due_at=now + timedelta(days=3))]
    merge.apply(conn, items, "syllabus", now)
    notes_dir = cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes"
    notes_dir.mkdir()
    (notes_dir / "Ch 4 lecture.md").write_text("# Forces\n")
    assert readiness.chapter_numbers("Read chapters 4-5 and Ch. 7") == [4, 5, 7]
    assert readiness.chapters_without_notes(conn, cfg, cfg.courses[0], now + timedelta(days=3)) == [5]
    [f] = readiness.flags(conn, cfg, now)
    assert "no notes yet on assigned ch. 5" in f["reasons"]


def test_scanned_handout_is_recognized(env, monkeypatch, tmp_path):
    from oso import convert

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "read_images", lambda ps: ["Worksheet 3: projectile problems" for _ in ps])
    blank = tmp_path / "handout.pdf"
    Image.new("L", (600, 800), 255).save(blank)
    text = convert._recognize_scan(blank)
    assert "## p. 1\n\nWorksheet 3: projectile problems" in text and "Scanned" in text


def test_the_computers_own_text_recognition():
    """Runs where the operating system has a recognizer (Windows and macOS test machines); skipped elsewhere."""
    from PIL import ImageDraw, ImageFont

    if not ocr.available():
        pytest.skip("no text recognizer on this computer")
    img = Image.new("RGB", (1400, 300), "white")
    try:
        font = ImageFont.load_default(size=72)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(img).text((40, 100), "Velocity and acceleration", fill="black", font=font)
    path = Path(__import__("tempfile").mkdtemp()) / "page.png"
    img.save(path)
    try:
        text = ocr.read_image(path)
    except ocr.OcrUnavailable as e:
        pytest.skip(str(e))
    assert "velocity" in text.lower() or "acceleration" in text.lower(), text
