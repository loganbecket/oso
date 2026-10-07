import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from oso import config as cfgmod, courses, db, sites, today
from oso.config import Config, Course

SITE = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private/\n"),
    "/~lee/phys110/": (200, "text/html", """<html><head><title>PHYS 110 - Dr. Lee</title><script>a</script></head><body>
        <nav><a href="/">University home</a></nav>
        <h1>General Physics</h1><p>Welcome to PHYS 110. Office hours are Tuesdays at 2 pm in room 210. Homework is posted below each week, along with lecture slides and solutions to the practice problems.</p>
        <ul><li><a href="week5.html">Week 5</a></li><li><a href="hw6.pdf">Homework 6</a></li><li><a href="/~lee/other/">Other course</a></li>
        <li><a href="/private/secret.html">Private</a></li><li><a href="https://elsewhere.example/x.html">Elsewhere</a></li></ul></body></html>"""),
    "/~lee/phys110/week5.html": (200, "text/html", "<html><head><title>Week 5</title></head><body><h2>Week 5: Forces</h2><p>Read chapter 5 before Monday. The slides from Tuesday's lecture are linked here, and the quiz on Friday covers friction and normal forces in some detail.</p><a href='slides5.pptx'>Slides</a></body></html>"),
    "/~lee/phys110/hw6.pdf": (200, "application/pdf", "%PDF-1.4 homework six"),
    "/~lee/phys110/slides5.pptx": (200, "application/vnd.ms-powerpoint", "PPTX slides"),
    "/~lee/other/": (200, "text/html", "<html><body>Another course entirely, which Oso should not read.</body></html>"),
    "/private/secret.html": (200, "text/html", "<html><body>Secret</body></html>"),
    "/locked/": (200, "text/html", "<html><body><form><input type='password' name='p'></form></body></html>"),
    "/app/": (200, "text/html", "<html><head><script src=a.js></script><script src=b.js></script><script src=c.js></script></head><body><div id=root></div></body></html>"),
}
HITS: list[str] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append(self.path)
        if self.path not in SITE:
            self.send_response(404)
            self.end_headers()
            return
        code, ctype, body = SITE[self.path]
        etag = f'"{hash(body) & 0xffff}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def env(tmp_path: Path, monkeypatch, server):
    monkeypatch.setattr(sites, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(cfgmod, "save", lambda c, path=None: None)
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(db, "data_dir", lambda: tmp_path / "data")
    (tmp_path / "data").mkdir()
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    HITS.clear()
    return cfg, server


def test_follow_a_site_pages_documents_and_manners(env):
    cfg, server = env
    courses.update(cfg, "PHYS-110", add_site=f"{server}/~lee/phys110/")
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    with db.connect() as conn:
        c = sites.check(cfg, conn, now)
        assert c == {"sites": 1, "pages_changed": 2, "files": 2, "problems": 0}
        web = next((cfg.vault / "Courses/2026 Fall/Physics/Web").iterdir())
        main = (web / "PHYS 110 - Dr. Lee.md").read_text(encoding="utf-8")
        assert "type: web-page" in main and "# General Physics" in main and "Office hours" in main and "University home" not in main
        assert (web / "Week 5.md").exists()
        assert (web / "files" / "hw6.pdf").read_bytes() == b"%PDF-1.4 homework six" and (web / "files" / "slides5.pptx").exists()
        assert "/~lee/other/" not in HITS and "/private/secret.html" not in HITS  # outside the course's folder; disallowed by robots.txt
        assert [r["text"] for r in sites.recent_events(conn, now + timedelta(hours=1))] == [
            f"Now following {server[7:]}/~lee/phys110: 2 pages and 2 files saved"]
        # not due again for a few hours; then only what changed is fetched again
        assert sites.check(cfg, conn, now + timedelta(hours=1))["sites"] == 0
        HITS.clear()
        SITE["/~lee/phys110/week5.html"] = (200, "text/html", SITE["/~lee/phys110/week5.html"][2].replace("Slides</a>", "Slides</a> <a href='hw7.pdf'>Homework 7</a>"))
        SITE["/~lee/phys110/hw7.pdf"] = (200, "application/pdf", "%PDF-1.4 seven")
        c = sites.check(cfg, conn, now + timedelta(hours=7))
        assert c["pages_changed"] == 1 and c["files"] == 1
        texts = [r["text"] for r in sites.recent_events(conn, now + timedelta(hours=8))]
        assert '127.0.0.1' in texts[-1] and texts[-1].endswith("has a new file: hw7.pdf") and any('"Week 5" changed' in t for t in texts)
        md = today.render(conn, cfg, now + timedelta(hours=8))
        assert "## From instructors' websites" in md and "hw7.pdf" in md


def test_sign_in_and_browser_only_pages_are_reported(env):
    cfg, server = env
    courses.update(cfg, "PHYS-110", add_site=f"{server}/locked/")
    courses.update(cfg, "PHYS-110", add_site=f"{server}/app/")
    with db.connect() as conn:
        c = sites.check(cfg, conn, datetime(2026, 11, 2, tzinfo=UTC))
        assert c["problems"] == 2 and c["pages_changed"] == 0
        lines = sites.problems(conn, cfg)
        assert any("asks for a sign-in" in line for line in lines) and any("only shows its content in a web browser" in line for line in lines)
        assert not (cfg.vault / "Courses/2026 Fall/Physics/Web").exists()


def test_adding_and_removing(env):
    cfg, _ = env
    courses.update(cfg, "PHYS-110", add_site="faculty.example.edu/~lee")
    courses.update(cfg, "PHYS-110", add_site="https://faculty.example.edu/~lee")
    assert cfg.courses[0].sites == ["https://faculty.example.edu/~lee"]
    courses.update(cfg, "PHYS-110", remove_site="faculty.example.edu/~lee")
    assert cfg.courses[0].sites == []
    with pytest.raises(ValueError):
        courses.update(cfg, "PHYS-110", add_site="not a site")
