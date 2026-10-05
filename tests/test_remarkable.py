import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from oso import db, handwriting
from oso.config import Config
from oso.connectors.remarkable_usb import NotConnected, RemarkableUsb, last_pull

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>"

DOCS = {
    "": [
        {"ID": "f1", "VissibleName": "School", "Type": "CollectionType"},
        {"ID": "d0", "VissibleName": "Grocery list", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-01T00:00:00Z"},
    ],
    "f1": [
        {"ID": "d1", "VissibleName": "Physics week 3", "Type": "DocumentType", "fileType": "notebook", "ModifiedClient": "2026-10-04T10:00:00Z"},
        {"ID": "d2", "VissibleName": "Textbook", "Type": "DocumentType", "fileType": "pdf", "ModifiedClient": "2026-10-04T10:00:00Z"},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/documents/"):
            key = self.path[len("/documents/"):]
            body = json.dumps(DOCS.get(key, [])).encode()
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

    def log_message(self, *a):  # silence
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_pull_only_changed_notebooks_in_folder(tmp_path: Path):
    srv = serve()
    base = f"http://127.0.0.1:{srv.server_port}"
    cfg = Config(vault=tmp_path / "vault", remarkable_folder="School")
    with db.connect(tmp_path / "t.sqlite") as conn:
        tab = RemarkableUsb(cfg, base=base)
        assert tab.connected()
        assert tab.pull(conn) == 1
        files = sorted(p.name for p in (cfg.vault / "Inbox" / "Handwriting").iterdir())
        assert files == ["Physics week 3.pdf"]
        assert tab.pull(conn) == 0
        assert last_pull(conn) is not None
        DOCS["f1"][0]["ModifiedClient"] = "2026-10-05T10:00:00Z"
        assert tab.pull(conn) == 1
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
    from pypdf import PdfWriter

    cfg = Config(vault=tmp_path / "vault")
    folder = cfg.vault / "Inbox" / "Handwriting"
    folder.mkdir(parents=True)
    src = folder / "Notes.pdf"

    def write_pdf(n):
        w = PdfWriter()
        for _ in range(n):
            w.add_blank_page(width=100, height=100)
        with src.open("wb") as f:
            w.write(f)

    with db.connect(tmp_path / "t.sqlite") as conn:
        write_pdf(2)
        assert handwriting.queue_new(conn, cfg) == 2
        import os
        import time

        write_pdf(3)
        os.utime(src, (time.time() + 5, time.time() + 5))
        assert handwriting.queue_new(conn, cfg) == 1
        assert [p["page"] for p in handwriting.pending(conn)] == [1, 2, 3]
