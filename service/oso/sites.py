"""Instructors' own websites: followed for new and changed materials.

For each course, the student can name pages where an instructor posts materials (`add_course_site`, or
during course setup). A few times a day (`site_check_hours`), Oso visits each page and the pages it links
to one level down within the same part of the site, and:

- saves a readable copy of each page in `Courses/<course>/Web/<site>/`, rewritten only when the page
  changes
- downloads documents the pages link to (PDF, Word, PowerPoint, Excel, text) into
  `Courses/<course>/Web/<site>/files/`, where they are converted, searched, and read like any course file
- lists what is new in Today.md: "Physics: Dr. Lee's site has a new file, HW 6.pdf"

It is polite: it honors the site's robots.txt, asks the server whether anything changed before
downloading again, waits between requests, and identifies itself. No Claude usage. A page that needs a
sign-in, or that only shows content when run in a browser, is reported plainly instead of being saved
empty.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
import urllib.robotparser
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import requests

from . import notes, vault
from .config import Config

log = logging.getLogger("oso.sites")

AGENT = "Oso/1.0 (a student's study assistant, reading course materials; https://github.com/loganbecket/oso)"
DOCUMENTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".odp", ".ods", ".rtf", ".txt", ".md", ".epub"}
MAX_PAGES = 30          # per followed site: the page itself and up to this many linked pages
MAX_FILE_MB = 50
PAUSE_SECONDS = 1.0
TIMEOUT = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS site_pages (
    url          TEXT PRIMARY KEY,
    course       TEXT NOT NULL,
    root         TEXT NOT NULL,
    title        TEXT,
    content_hash TEXT,
    etag         TEXT,
    modified     TEXT,
    note         TEXT,
    status       TEXT NOT NULL DEFAULT 'ok',   -- ok, needs_sign_in, needs_browser, gone, error
    checked_at   TEXT,
    changed_at   TEXT
);
CREATE TABLE IF NOT EXISTS site_files (
    url        TEXT PRIMARY KEY,
    course     TEXT NOT NULL,
    root       TEXT NOT NULL,
    path       TEXT NOT NULL,
    etag       TEXT,
    modified   TEXT,
    size       INTEGER,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_events (
    id     INTEGER PRIMARY KEY,
    at     TEXT NOT NULL,
    course TEXT NOT NULL,
    text   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_roots (
    root       TEXT PRIMARY KEY,
    checked_at TEXT
);
"""


def ensure(conn: sqlite3.Connection) -> None:
    from . import schema

    schema.apply(conn)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---- reading HTML ---------------------------------------------------------------------------------------


class _Page(HTMLParser):
    """Links, title, and readable text of a page, without its navigation, scripts, and styles."""

    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "svg", "form"}
    BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self.parts: list[str] = []
        self.skip = 0
        self.in_title = False
        self.href: str | None = None
        self.link_text: list[str] = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            self.scripts += 1
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a" and a.get("href"):
            self.href, self.link_text = a["href"], []
        if not self.skip:
            if tag in ("h1", "h2", "h3"):
                self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
            elif tag == "li":
                self.parts.append("\n- ")
            elif tag in self.BLOCK:
                self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join("".join(self.link_text).split())))
            self.href = None

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.href is not None:
            self.link_text.append(data)
        if not self.skip and not self.in_title:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse(html: str) -> _Page:
    p = _Page()
    p.feed(html)
    p.close()
    return p


# ---- fetching ---------------------------------------------------------------------------------------------


class _Fetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = AGENT
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.last = 0.0

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        base = f"{u.scheme}://{u.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.get(base + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[base] = rp
        return self.robots[base].can_fetch(AGENT, url)

    def get(self, url: str, headers: dict | None = None, stream: bool = False) -> requests.Response:
        wait = PAUSE_SECONDS - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        if not public_url(url):
            raise requests.ConnectionError("not a public address")
        try:
            r = self.s.get(url, headers=headers or {}, timeout=TIMEOUT, stream=stream, allow_redirects=True)
        finally:
            self.last = time.monotonic()
        if not public_url(r.url):  # a redirect must not lead inside the network either
            r.close()
            raise requests.ConnectionError("redirected to a private address")
        return r


def _looks_like_sign_in(r: requests.Response, html: str) -> bool:
    if r.status_code in (401, 403):
        return True
    final = r.url.lower()
    if any(w in final for w in ("/login", "/signin", "/sign-in", "/sso", "/saml", "/cas/", "accounts.google.com")):
        return True
    return bool(re.search(r'<input[^>]+type=["\']?password', html, re.IGNORECASE))


def _within(root: str, url: str) -> bool:
    """A page in the same part of the site as the followed page: same host, under the same folder."""
    r, u = urlparse(root), urlparse(url)
    if r.netloc != u.netloc:
        return False
    folder = r.path if r.path.endswith("/") else r.path.rsplit("/", 1)[0] + "/"
    return u.path.startswith(folder)


def _ext(url: str) -> str:
    return Path(unquote(urlparse(url).path)).suffix.lower()


def _site_folder(cfg: Config, course: str, root: str) -> Path:
    c = cfg.course_for(course)
    host = urlparse(root).netloc
    path = urlparse(root).path.strip("/").replace("/", " ")
    name = notes.safe_name(f"{host} {path}".strip())[:80]
    return cfg.vault / "Courses" / (c.folder if c else course) / "Web" / name


# ---- the check ------------------------------------------------------------------------------------------


def due(conn: sqlite3.Connection, cfg: Config, root: str, now: datetime) -> bool:
    row = conn.execute("SELECT checked_at FROM site_roots WHERE root = ?", (root,)).fetchone()
    if not row or not row["checked_at"]:
        return True
    return now - datetime.fromisoformat(row["checked_at"]) >= timedelta(hours=cfg.site_check_hours)


def check(cfg: Config, conn: sqlite3.Connection, now: datetime | None = None, force: bool = False) -> dict[str, int]:
    ensure(conn)
    now = now or datetime.now(UTC)
    counts = {"sites": 0, "pages_changed": 0, "files": 0, "problems": 0}
    fetcher = _Fetcher()
    for c in cfg.courses:
        if c.finished:
            continue
        for root in c.sites:
            if not force and not due(conn, cfg, root, now):
                continue
            counts["sites"] += 1
            r = _check_site(cfg, conn, fetcher, c.code, root, now)
            for k in ("pages_changed", "files", "problems"):
                counts[k] += r[k]
            conn.execute("INSERT OR REPLACE INTO site_roots (root, checked_at) VALUES (?, ?)", (root, now.isoformat(timespec="seconds")))
            conn.commit()
    return counts


def _check_site(cfg: Config, conn: sqlite3.Connection, fetcher: _Fetcher, course: str, root: str, now: datetime) -> dict[str, int]:
    counts = {"pages_changed": 0, "files": 0, "problems": 0}
    first_time = conn.execute("SELECT 1 FROM site_pages WHERE root = ? LIMIT 1", (root,)).fetchone() is None
    folder = _site_folder(cfg, course, root)
    known = [r["url"] for r in conn.execute("SELECT url FROM site_pages WHERE root = ? AND url != ?", (root, root))]
    queue, seen, documents = [root, *known], set(), {}  # subpages found before are rechecked even when the main page is unchanged
    when = now.isoformat(timespec="seconds")
    while queue and len(seen) <= MAX_PAGES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not fetcher.allowed(url):
            _status(conn, course, root, url, "blocked", when)
            continue
        prev = conn.execute("SELECT * FROM site_pages WHERE url = ?", (url,)).fetchone()
        headers = {}
        if prev is not None and prev["etag"]:
            headers["If-None-Match"] = prev["etag"]
        if prev is not None and prev["modified"]:
            headers["If-Modified-Since"] = prev["modified"]
        try:
            r = fetcher.get(url, headers)
        except requests.RequestException as e:
            _status(conn, course, root, url, "error", when, note=type(e).__name__)
            counts["problems"] += 1
            continue
        if r.status_code == 304 and prev is not None:
            conn.execute("UPDATE site_pages SET checked_at = ? WHERE url = ?", (when, url))
            html = None
        elif r.status_code == 404 or r.status_code == 410:
            _status(conn, course, root, url, "gone", when)
            if url == root:
                counts["problems"] += 1
            continue
        elif r.status_code >= 400 and r.status_code not in (401, 403):
            _status(conn, course, root, url, "error", when, note=f"the site answered {r.status_code}")
            counts["problems"] += 1
            continue
        else:
            html = r.text if "html" in (r.headers.get("Content-Type") or "html") else None
        if html is None and r.status_code != 304:
            continue
        if html is not None:
            if _looks_like_sign_in(r, html):
                _status(conn, course, root, url, "needs_sign_in", when)
                counts["problems"] += url == root
                continue
            page = parse(html)
            text = page.text()
            if len(text) < 200 and page.scripts >= 3:
                _status(conn, course, root, url, "needs_browser", when)
                counts["problems"] += url == root
                continue
            title = " ".join(unescape(page.title).split()) or urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            changed = prev is None or prev["content_hash"] != digest
            if changed:
                folder.mkdir(parents=True, exist_ok=True)
                note = folder / _note_name(root, url, title)
                fm = {"type": "web-page", "course": course, "source": url, "fetched": now.isoformat(timespec="minutes")}
                vault.write_note(note, fm, f"# {title}\n\n{text}\n", vault.web_page)
                counts["pages_changed"] += 1
                if prev is not None and not first_time:
                    _event(conn, course, when, f"{_site_name(root)}: \"{title}\" changed")
            conn.execute(
                """INSERT INTO site_pages (url, course, root, title, content_hash, etag, modified, status, checked_at, changed_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, NULL)
                   ON CONFLICT(url) DO UPDATE SET title = excluded.title, content_hash = excluded.content_hash, etag = excluded.etag,
                     modified = excluded.modified, status = 'ok', note = NULL, checked_at = excluded.checked_at,
                     changed_at = CASE WHEN site_pages.content_hash IS excluded.content_hash THEN site_pages.changed_at ELSE excluded.checked_at END""",
                (url, course, root, title, digest, r.headers.get("ETag"), r.headers.get("Last-Modified"), when, when),
            )
            for href, label in page.links:
                link = urldefrag(urljoin(r.url, href.strip()))[0]
                if not link.startswith(("http://", "https://")):
                    continue
                if _ext(link) in DOCUMENTS and public_url(link):
                    documents.setdefault(link, label)
                elif url == root and _within(root, link) and _ext(link) in ("", ".html", ".htm", ".php", ".asp", ".aspx"):
                    queue.append(link)
    for link, label in documents.items():
        if not fetcher.allowed(link):
            continue
        got = _fetch_file(cfg, conn, fetcher, course, root, folder, link, when)
        if got:
            counts["files"] += 1
            if not first_time:
                _event(conn, course, when, f"{_site_name(root)} has {'a new' if got == 'new' else 'an updated'} file: {Path(unquote(urlparse(link).path)).name}")
    if first_time:
        n_files = conn.execute("SELECT COUNT(*) FROM site_files WHERE root = ?", (root,)).fetchone()[0]
        n_pages = conn.execute("SELECT COUNT(*) FROM site_pages WHERE root = ? AND status = 'ok'", (root,)).fetchone()[0]
        if n_pages:
            _event(conn, course, when, f"Now following {_site_name(root)}: {n_pages} page{'s' if n_pages != 1 else ''}"
                                       f" and {n_files} file{'s' if n_files != 1 else ''} saved")
    return counts


def _fetch_file(cfg, conn, fetcher, course, root, folder, url, when) -> str | None:
    """Download a linked document if it is new or changed. Returns 'new', 'updated', or None."""
    prev = conn.execute("SELECT * FROM site_files WHERE url = ?", (url,)).fetchone()
    headers = {}
    if prev is not None and prev["etag"]:
        headers["If-None-Match"] = prev["etag"]
    if prev is not None and prev["modified"]:
        headers["If-Modified-Since"] = prev["modified"]
    try:
        r = fetcher.get(url, headers, stream=True)
    except requests.RequestException:
        return None
    with r:
        if r.status_code == 304 or r.status_code >= 400:
            return None
        size = int(r.headers.get("Content-Length") or 0)
        if size > MAX_FILE_MB * 1024 * 1024:
            return None
        if prev is not None and size and prev["size"] == size and not r.headers.get("ETag") and not r.headers.get("Last-Modified"):
            return None
        name = notes.safe_name(Path(unquote(urlparse(url).path)).name, limit=120) or "file"
        dest = folder / "files" / name
        if prev is None and dest.exists():  # another address on the site has a document of the same name
            dest = dest.with_name(f"{dest.stem} {_short(url)}{dest.suffix}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        written = 0
        try:
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    written += len(chunk)
                    if written > MAX_FILE_MB * 1024 * 1024:
                        break
                    f.write(chunk)
        except (requests.RequestException, OSError):
            tmp.unlink(missing_ok=True)
            return None
        if written > MAX_FILE_MB * 1024 * 1024:
            tmp.unlink(missing_ok=True)
            return None
        if prev is not None and dest.exists() and dest.read_bytes() == tmp.read_bytes():
            tmp.unlink()
            conn.execute("UPDATE site_files SET etag = ?, modified = ? WHERE url = ?", (r.headers.get("ETag"), r.headers.get("Last-Modified"), url))
            return None
        tmp.replace(dest)
    conn.execute(
        """INSERT INTO site_files (url, course, root, path, etag, modified, size, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET path = excluded.path, etag = excluded.etag, modified = excluded.modified,
             size = excluded.size, fetched_at = excluded.fetched_at""",
        (url, course, root, dest.relative_to(cfg.vault).as_posix(), r.headers.get("ETag"), r.headers.get("Last-Modified"), written, when),
    )
    return "updated" if prev is not None else "new"


def _status(conn, course, root, url, status, when, note=None) -> None:
    conn.execute(
        """INSERT INTO site_pages (url, course, root, status, checked_at, note) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(url) DO UPDATE SET status = excluded.status, checked_at = excluded.checked_at, note = excluded.note""",
        (url, course, root, status, when, note),
    )


def _event(conn, course, when, text) -> None:
    conn.execute("INSERT INTO site_events (at, course, text) VALUES (?, ?, ?)", (when, course, text))


def _site_name(root: str) -> str:
    u = urlparse(root)
    return u.netloc + (u.path.rstrip("/") if u.path not in ("", "/") else "")


# ---- reading it back --------------------------------------------------------------------------------------

PROBLEMS = {
    "needs_sign_in": "asks for a sign-in, so Oso can't read it",
    "needs_browser": "only shows its content in a web browser, so Oso can't read it",
    "gone": "no longer exists",
    "error": "could not be reached",
    "blocked": "asks automated visitors not to read it",
}


def recent_events(conn: sqlite3.Connection, now: datetime, hours: int = 24) -> list[sqlite3.Row]:
    ensure(conn)
    since = (now - timedelta(hours=hours)).astimezone(UTC).isoformat(timespec="seconds")
    return conn.execute("SELECT at, course, text FROM site_events WHERE at >= ? ORDER BY at", (since,)).fetchall()


def problems(conn: sqlite3.Connection, cfg: Config) -> list[str]:
    """Plain lines for followed pages Oso can't read (the followed page itself, not its subpages)."""
    ensure(conn)
    out = []
    for c in cfg.courses:
        if c.finished:
            continue
        for root in c.sites:
            row = conn.execute("SELECT status, note FROM site_pages WHERE url = ?", (root,)).fetchone()
            if row and row["status"] in PROBLEMS:
                out.append(f"**{c.name}**: {_site_name(root)} {PROBLEMS[row['status']]}" + (f" ({row['note']})" if row["note"] else "") + ".")
    return out


def status(conn: sqlite3.Connection, cfg: Config) -> list[dict]:
    ensure(conn)
    out = []
    for c in cfg.courses:
        for root in c.sites:
            row = conn.execute("SELECT status, checked_at FROM site_pages WHERE url = ?", (root,)).fetchone()
            files = conn.execute("SELECT COUNT(*) FROM site_files WHERE root = ?", (root,)).fetchone()[0]
            pages = conn.execute("SELECT COUNT(*) FROM site_pages WHERE root = ? AND status = 'ok'", (root,)).fetchone()[0]
            out.append({"course": c.code, "site": root, "status": row["status"] if row else "not checked yet",
                        "checked_at": row["checked_at"] if row else None, "pages": pages, "files": files})
    return out


def _short(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:6]


def _note_name(root: str, url: str, title: str) -> str:
    """The followed page keeps its title as its name; every other page carries a short tag from its address, so
    two pages with the same title (most faculty sites title every page after the course) do not overwrite each other."""
    base = notes.safe_name(title)[:72]
    return f"{base}.md" if url == root else f"{base} {_short(url)}.md"


def normalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    u = urlparse(url)
    if not u.netloc or "." not in u.netloc or not u.hostname:
        raise ValueError(f"{url!r} doesn't look like a web address.")
    if not public_host(u.hostname):
        raise ValueError(f"{url!r} points inside a private network, which Oso doesn't read.")
    return urldefrag(url)[0]


ALLOW_LOCAL = False  # tests run their sites on this computer


def public_host(host: str) -> bool:
    """A name or address on the public internet. Anything on this computer, a home or campus network, or the
    link-local range (where cloud machines keep their credentials) is refused, so that a page or message can never
    make Oso fetch something only this computer can reach."""
    import ipaddress
    import socket

    if ALLOW_LOCAL:
        return True
    host = (host or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, None)]
        except (socket.gaierror, OSError, ValueError):
            return False
    return bool(addresses) and all(a.is_global and not a.is_multicast for a in addresses)


def public_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and bool(u.hostname) and public_host(u.hostname)
