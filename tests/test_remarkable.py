import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from oso import db, handwriting
from oso.config import Config, Course
from oso.connectors.remarkable_usb import NotConnected, RemarkableUsb, last_pull

from test_notes_and_convert import inked_pdf  # noqa: E402

_tmp = Path(__file__).parent / ".inked.pdf"
inked_pdf(_tmp)
PDF = _tmp.read_bytes()
_tmp.unlink()

DOCS = {
    "": [
        {"ID": "f-phys", "VissibleName": "Physics", "Type": "CollectionType"},
        {"ID": "f-personal", "VissibleName": "Journal", "Type": "CollectionType"},
        {"ID": "d-loose", "VissibleName": "Grocery list", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-01T00:00:00Z"},
    ],
    "f-phys": [
        {"ID": "d1", "VissibleName": "Week 3", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-04T10:00:00Z"},
        {"ID": "d2", "VissibleName": "Textbook", "Type": "DocumentType", "fileType": "pdf", "ModifiedClient": "2026-10-04T10:00:00Z"},
        {"ID": "f-labs", "VissibleName": "Labs", "Type": "CollectionType"},
    ],
    "f-labs": [
        {"ID": "d3", "VissibleName": "Lab 1", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-04T10:00:00Z"},
    ],
    "f-personal": [
        {"ID": "d4", "VissibleName": "Diary", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-04T10:00:00Z"},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/documents/"):
            body = json.dumps(DOCS.get(self.path[len("/documents/"):], [])).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/download/") and self.path.endswith("/pdf"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(PDF)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_pull_only_course_folders_into_their_course(tmp_path: Path):
    srv = serve()
    base = f"http://127.0.0.1:{srv.server_port}"
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    with db.connect(tmp_path / "t.sqlite") as conn:
        tab = RemarkableUsb(cfg, base=base)
        assert tab.connected()
        assert tab.pull(conn) == 2
        hw = cfg.vault / "Courses" / "Physics" / "Handwriting"
        assert (hw / "Week 3.pdf").exists()
        assert (hw / "Labs" / "Lab 1.pdf").exists()
        assert not (cfg.vault / "Inbox" / "Handwriting").exists()
        assert not list(cfg.vault.rglob("Diary.pdf")) and not list(cfg.vault.rglob("Grocery list.pdf"))
        assert tab.pull(conn) == 0
        assert last_pull(conn) is not None
        DOCS["f-phys"][0]["ModifiedClient"] = "2026-10-05T10:00:00Z"
        assert tab.pull(conn) == 1

        # The queue tags pages with the course the folder belongs to.
        assert handwriting.queue_new(conn, cfg) == 2
        pend = handwriting.pending(conn)
        assert {p["course"] for p in pend} == {"PHYS-110"}
        assert {p["notebook"] for p in pend} == {"Week 3", "Lab 1"}
    srv.shutdown()


def test_not_connected_is_not_an_error(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault")
    with db.connect(tmp_path / "t.sqlite") as conn:
        tab = RemarkableUsb(cfg, base="http://127.0.0.1:9")
        assert not tab.connected()
        try:
            tab.pull(conn)
            raise AssertionError("expected NotConnected")
        except NotConnected:
            pass


def test_requeue_only_new_pages_after_redownload(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    folder = cfg.vault / "Courses" / "Physics" / "Handwriting"
    folder.mkdir(parents=True)
    src = folder / "Notes.pdf"

    def write_pdf(n):
        inked_pdf(src, pages=n)

    with db.connect(tmp_path / "t.sqlite") as conn:
        write_pdf(2)
        assert handwriting.queue_new(conn, cfg) == 2
        write_pdf(3)
        os.utime(src, (time.time() + 5, time.time() + 5))
        assert handwriting.queue_new(conn, cfg) == 1
        pend = handwriting.pending(conn)
        assert [p["page"] for p in pend] == [1, 2, 3]
        assert pend[0]["course"] == "PHYS-110"
