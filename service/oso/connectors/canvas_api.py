"""Canvas REST API, read with the student's own signed-in session (canvas_session.py) or, where a
school allows one, an access token.

Adds what the calendar feed cannot: grade weights, points, submissions and grades, late and missing
flags, instructor comments, current course grades, announcements, and the course files, which are
mirrored into the vault. `fetch` gathers it all in one pass; `canvas_store.save` keeps it in the database.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from .. import notes
from ..config import Config
from ..db import Item

log = logging.getLogger("oso.canvas_api")

NAME = "canvas_api"
MAX_FILE_MB = 50
ANNOUNCEMENT_NEWS = timedelta(days=3)  # an announcement newer than this is read for schedule changes


class SessionExpired(Exception):
    """Canvas no longer accepts the signed-in session; the student has to sign in again."""


class CanvasApi:
    name = NAME

    def __init__(self, base_url: str, token: str | None, cfg: Config, timeout: float = 30.0,
                 cookies: dict[str, str] | None = None):
        self.base = base_url.rstrip("/")
        self.cfg = cfg
        self.tz: ZoneInfo = cfg.tz
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        host = urlparse(self.base).hostname or ""
        for k, v in (cookies or {}).items():
            # Tied to the Canvas host, so a session Canvas refreshes replaces this one instead of sitting beside it.
            self.s.cookies.set(k, v, domain=host, path="/")
        self.uses_session = bool(cookies) and not token
        self.grades: dict[str, tuple[float | None, float | None]] = {}
        self.weights: dict[str, float] = {}
        # Raw records from the last fetch, for canvas_store.
        self.courses: list[dict] = []
        self.groups: dict[str, dict] = {}
        self.assignments: list[dict] = []
        self.submissions: list[dict] = []

    def cookies(self) -> dict[str, str]:
        """The session as Canvas last refreshed it."""
        return {c.name: c.value for c in self.s.cookies}

    # ---- items -------------------------------------------------------------------------------

    def fetch(self) -> list[Item]:
        items: list[Item] = []
        self.courses, self.groups, self.assignments, self.submissions = [], {}, [], []
        for course in self._courses():
            self.courses.append(course)
            code = course.get("course_code") or str(course["id"])
            known = self.cfg.resolve(code)
            if known is not None:
                code = known.code  # Oso's own code for the course, so grades, topics, and notes line up
            self._load_group_weights(course["id"])
            for a in self._pages(f"/api/v1/courses/{course['id']}/assignments", {"include[]": "submission", "per_page": 100}):
                a["_course_code"] = code
                self.assignments.append(a)
                items.append(self._assignment(a, code))
            try:  # his submissions; a course that hides them is skipped, not fatal
                for sub in self._pages(f"/api/v1/courses/{course['id']}/students/submissions",
                                       [("student_ids[]", "self"), ("include[]", "submission_comments"),
                                        ("include[]", "submission_history"), ("per_page", 100)]):
                    sub["_course_code"] = code
                    self.submissions.append(sub)
            except requests.HTTPError:
                pass
        return items

    def _courses(self) -> list[dict]:
        params = [("enrollment_state", "active"), ("per_page", 50), ("include[]", "total_scores"), ("include[]", "term")]
        return [c for c in self._pages("/api/v1/courses", params) if "course_code" in c]

    def _load_group_weights(self, course_id: int) -> None:
        self.weights = {}
        try:
            for g in self._pages(f"/api/v1/courses/{course_id}/assignment_groups", {"per_page": 50}):
                self.groups[str(g["id"])] = g
                if g.get("group_weight"):
                    self.weights[str(g["id"])] = float(g["group_weight"])
        except requests.HTTPError:
            pass

    def _assignment(self, a: dict, code: str) -> Item:
        due = _parse_time(a.get("due_at"), self.tz)
        title = (a.get("name") or "Untitled assignment").strip()
        kind = "quiz" if a.get("is_quiz_assignment") or "online_quiz" in (a.get("submission_types") or []) else "assignment"
        if re.search(r"\b(exam|midterm|final|test)\b", title, re.IGNORECASE):
            kind = "exam"
        ext = f"assignment-{a['id']}"
        sub = a.get("submission") or {}
        if sub.get("score") is not None:
            self.grades[ext] = (float(sub["score"]), float(a.get("points_possible") or 0) or None)
        weight = self.weights.get(str(a.get("assignment_group_id")))
        category = (self.groups.get(str(a.get("assignment_group_id"))) or {}).get("name")
        return Item(
            source=NAME,
            external_id=ext,
            kind=kind,
            title=title,
            due_at=due,
            all_day=False,
            course_code=code,
            url=a.get("html_url"),
            description=_strip_html(a.get("description") or "")[:2000] or None,
            weight=weight,
            category=category,
        )

    # ---- vault mirroring ---------------------------------------------------------------------

    def mirror(self) -> dict[str, int]:
        """Download course materials into the vault: everything linked in the course's modules (where most
        instructors put their files), the Files section, and announcements. Safe to run on every check."""
        counts = {"files": 0, "module_files": 0, "module_pages": 0, "announcements": 0}
        self.new_files: list[tuple[str, str]] = []  # (course code, plain description) for Today.md
        self.new_announcements: list[dict] = []  # recent announcements and inbox messages, read by Claude like email (messages.py)
        for course in self.courses or self._courses():
            code = course.get("course_code") or str(course["id"])
            folder = notes.course_dir(self.cfg, code)
            if folder is None:
                continue  # course not set up in Oso yet
            seen: set[int] = set()
            m = self._mirror_modules(course["id"], code, folder / "Canvas" / "Modules", seen)
            counts["module_files"] += m["files"]
            counts["module_pages"] += m["pages"]
            counts["files"] += self._mirror_files(course["id"], code, folder / "Canvas", seen)
            counts["announcements"] += self._mirror_announcements(course["id"], code, folder / "Announcements")
        counts["inbox"] = self._inbox()
        return counts

    def _inbox(self) -> int:
        """Recent messages instructors sent him in the Canvas inbox (Canvas emails only a notice that one arrived).
        Read without marking them read in Canvas."""
        recent = datetime.now(self.tz) - ANNOUNCEMENT_NEWS
        try:
            me = (self._one("/api/v1/users/self", {}) or [{}])[0].get("id")
            convs = self._one("/api/v1/conversations", {"scope": "inbox", "per_page": 20})
        except requests.HTTPError:
            return 0
        codes = {f"course_{c['id']}": c.get("course_code") for c in self.courses}
        n = 0
        for c in convs:
            last = _parse_time(c.get("last_message_at"), self.tz)
            if not last or last < recent:
                continue
            try:
                full = (self._one(f"/api/v1/conversations/{c['id']}", {"auto_mark_as_read": "false"}) or [{}])[0]
            except requests.HTTPError:
                continue
            names = {p.get("id"): p.get("name") for p in full.get("participants", [])}
            raw = codes.get(full.get("context_code") or c.get("context_code") or "")
            course = self.cfg.resolve(raw) if raw else None
            for m in full.get("messages", []):
                at = _parse_time(m.get("created_at"), self.tz)
                if not at or at < recent or (me is not None and m.get("author_id") == me):
                    continue
                self.new_announcements.append({
                    "source": "canvas", "external_id": f"msg:{m.get('id')}", "sender": names.get(m.get("author_id")) or "Canvas inbox",
                    "subject": full.get("subject") or c.get("subject"), "channel": course.code if course else (raw or None),
                    "sent_at": at.isoformat(timespec="minutes"), "text": _strip_html(m.get("body") or "")[:6000],
                    "link": f"{self.base}/conversations",
                })
                n += 1
        return n

    # ---- modules -------------------------------------------------------------------------------

    def _mirror_modules(self, course_id: int, code: str, dest: Path, seen: set[int]) -> dict[str, int]:
        """Every module, in order, as a folder: its files downloaded, its pages saved as notes, and an index
        note listing all of it (with outside links). Locked items are skipped until they open."""
        counts = {"files": 0, "pages": 0}
        try:
            modules = self._pages(f"/api/v1/courses/{course_id}/modules", [("include[]", "items"), ("per_page", 50)])
        except requests.HTTPError:
            return counts  # modules hidden in this course
        index = ["# Modules", "", "From Canvas, kept up to date by Oso.", ""]
        for n, mod in enumerate(sorted(modules, key=lambda m: m.get("position") or 0), start=1):
            name = (mod.get("name") or f"Module {n}").strip()
            folder = dest / f"{n:02d} {notes.safe_name(name)[:70]}"
            items = mod.get("items")
            if items is None and mod.get("items_url"):
                try:
                    items = self._pages(mod["items_url"], {"per_page": 100})
                except requests.HTTPError:
                    items = []
            index.append(f"## {name}")
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                kind, title = item.get("type"), (item.get("title") or "").strip()
                if kind == "File" and item.get("content_id"):
                    got = self._module_file(course_id, code, int(item["content_id"]), folder, seen, name)
                    counts["files"] += got is not None and got[1]
                    index.append(f"- {title}" + (f" ([[{got[0]}]])" if got else " (locked or unavailable)"))
                elif kind == "Page" and item.get("page_url"):
                    path = self._module_doc(course_id, code, f"/api/v1/courses/{course_id}/pages/{item['page_url']}",
                                            "body", folder, title, name, seen, counts)
                    index.append(f"- [[{path}|{title}]]" if path else f"- {title} (locked or unavailable)")
                elif kind in ("Assignment", "Quiz", "Discussion") and item.get("content_id"):
                    endpoint, field = {
                        "Assignment": (f"/api/v1/courses/{course_id}/assignments/{item['content_id']}", "description"),
                        "Quiz": (f"/api/v1/courses/{course_id}/quizzes/{item['content_id']}", "description"),
                        "Discussion": (f"/api/v1/courses/{course_id}/discussion_topics/{item['content_id']}", "message"),
                    }[kind]
                    path = self._module_doc(course_id, code, endpoint, field, folder, title, name, seen, counts, kind=kind.lower())
                    index.append(f"- {kind}: [[{path}|{title}]]" if path else f"- {kind}: {title}")
                elif kind == "ExternalUrl" and item.get("external_url"):
                    url = item["external_url"]
                    if _doc_link(url):
                        target = folder / notes.safe_name(Path(url.split("?")[0]).name, limit=120)
                        got = not target.exists() and self._download(url, target)  # an outside document: fetched once
                        counts["files"] += got
                        if got:
                            self.new_files.append((code, f"New file in {name}: {Path(url.split('?')[0]).name}"))
                    index.append(f"- [{title or url}]({url})")
                elif kind == "SubHeader":
                    index.append(f"### {title}")
                elif title:
                    index.append(f"- {title}" + (f" ({item['html_url']})" if item.get("html_url") else ""))
            index.append("")
        if modules:
            dest.mkdir(parents=True, exist_ok=True)
            text = notes.with_front_matter({"type": "canvas-modules", "course": code}, "\n".join(index) + "\n")
            target = dest / "Modules.md"
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                target.write_text(text, encoding="utf-8")
        return counts

    def _module_file(self, course_id: int, code: str, file_id: int, folder: Path, seen: set[int], module: str):
        """Download one file a module links to. Returns (vault path, downloaded now) or None."""
        seen.add(file_id)
        try:
            f = self._pages(f"/api/v1/courses/{course_id}/files/{file_id}", {})
        except requests.HTTPError:
            return None
        if not f:
            return None
        f = f[0]
        if f.get("locked_for_user") or not f.get("url") or (f.get("size") or 0) > MAX_FILE_MB * 1024 * 1024:
            return None
        name = notes.safe_name(f.get("display_name") or f.get("filename") or str(file_id), limit=120)
        target = folder / name
        stamp = _parse_time(f.get("updated_at"), self.tz)
        fresh = not (target.exists() and stamp and target.stat().st_mtime >= stamp.timestamp())
        if fresh:
            if not self._download(f["url"], target):
                return None
            self.new_files.append((code, f"New file in {module}: {name}"))
        return (target.relative_to(self.cfg.vault).as_posix(), fresh)

    def _module_doc(self, course_id: int, code: str, endpoint: str, field: str, folder: Path, title: str, module: str,
                    seen: set[int], counts: dict, kind: str = "page") -> str | None:
        """A module page, or an assignment, quiz, or discussion's instructions: saved as a note, and every
        file it links to (Canvas files and outside documents) downloaded into the module's folder."""
        try:
            got = self._pages(endpoint, {})
        except requests.HTTPError:
            return None
        if not got or got[0].get("locked_for_user"):
            return None
        doc = got[0]
        html = doc.get(field) or ""
        files = []
        for fid in _canvas_file_ids(html):
            res = self._module_file(course_id, code, fid, folder, seen, module)
            if res:
                files.append(res[0])
                counts["files"] += res[1]
        for url in _doc_links(html, self.base):
            target = folder / notes.safe_name(Path(url.split("?")[0]).name, limit=120)
            if not target.exists() and self._download(url, target):
                counts["files"] += 1
                self.new_files.append((code, f"New file in {module}: {target.name}"))
            if target.exists():
                files.append(target.relative_to(self.cfg.vault).as_posix())
        heading = doc.get("title") or doc.get("name") or title
        body = f"# {heading}\n\n{_strip_html(html)}\n"
        if files:
            body += "\n## Files linked here\n\n" + "\n".join(f"- [[{f}]]" for f in dict.fromkeys(files)) + "\n"
        prefix = "" if kind == "page" else f"{kind.title()} - "
        target = folder / f"{prefix}{notes.safe_name(heading)[:80]}.md"
        fm = {"type": f"canvas-{kind}", "updated": doc.get("updated_at"), "due": doc.get("due_at"), "source": doc.get("html_url")}
        text = notes.with_front_matter(fm, body)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            counts["pages"] += 1
        return target.relative_to(self.cfg.vault).with_suffix("").as_posix()

    def _download(self, url: str, target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        # The student's sign-in (token or cookies) goes only to Canvas itself. A document an instructor linked on
        # another site is fetched with a bare request, so that site never sees his Canvas credentials.
        own = urlparse(url).hostname == urlparse(self.base).hostname
        if not own:
            from ..sites import public_url

            if not public_url(url):
                log.warning("not downloading %s: not a public address", target.name)
                return False
        client = self.s if own else requests
        try:
            with client.get(url, stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                with tmp.open("wb") as out:
                    for chunk in r.iter_content(1 << 16):
                        out.write(chunk)
            tmp.replace(target)
            return True
        except (requests.RequestException, OSError) as e:
            log.warning("could not download %s: %s", target.name, type(e).__name__)
            tmp.unlink(missing_ok=True)
            return False

    # ---- the Files section ---------------------------------------------------------------------

    def _mirror_files(self, course_id: int, code: str, dest: Path, seen: set[int]) -> int:
        n = 0
        try:
            files = self._pages(f"/api/v1/courses/{course_id}/files", {"per_page": 100})
        except requests.HTTPError:
            return 0  # Files hidden in this course; modules usually have everything
        for f in files:
            if f.get("id") in seen:
                continue  # already downloaded from a module
            if (f.get("size") or 0) > MAX_FILE_MB * 1024 * 1024 or f.get("locked_for_user") or not f.get("url"):
                continue
            name = notes.safe_name(f.get("display_name") or f.get("filename") or str(f["id"]), limit=120)
            target = dest / name
            stamp = _parse_time(f.get("updated_at"), self.tz)
            if target.exists() and stamp and target.stat().st_mtime >= stamp.timestamp():
                continue
            if self._download(f["url"], target):
                n += 1
                self.new_files.append((code, f"New file: {name}"))
        return n

    def _mirror_announcements(self, course_id: int, code: str, dest: Path) -> int:
        n = 0
        recent = datetime.now(self.tz) - ANNOUNCEMENT_NEWS
        try:
            anns = self._pages("/api/v1/announcements", {"context_codes[]": f"course_{course_id}", "per_page": 50})
        except requests.HTTPError:
            return 0
        for a in anns:
            posted = _parse_time(a.get("posted_at"), self.tz)
            day = posted.strftime("%Y-%m-%d") if posted else "undated"
            target = dest / f"{day} {notes.safe_name(a.get('title') or 'Announcement')}.md"
            if target.exists():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            fm = {"type": "announcement", "posted": posted.isoformat(timespec="minutes") if posted else None, "source": a.get("html_url")}
            body = f"# {a.get('title', 'Announcement')}\n\n{_strip_html(a.get('message') or '')}\n"
            target.write_text(notes.with_front_matter(fm, body), encoding="utf-8")
            n += 1
            if posted and posted >= recent:  # older ones are history, not news
                course = self.cfg.resolve(code)
                self.new_announcements.append({
                    "source": "canvas", "external_id": str(a.get("id") or target.name), "sender": course.name if course else code,
                    "subject": a.get("title"), "channel": course.code if course else code, "sent_at": posted.isoformat(timespec="minutes"),
                    "text": _strip_html(a.get("message") or "")[:6000], "link": a.get("html_url"),
                })
        return n

    # ---- http --------------------------------------------------------------------------------

    def _one(self, path: str, params) -> list[dict]:
        """One page only (the inbox goes back years)."""
        r = self.s.get(self.base + path, params=params, timeout=self.timeout, allow_redirects=not self.uses_session)
        if self.uses_session and _signed_out(r):
            raise SessionExpired()
        r.raise_for_status()
        data = r.json()
        return [x for x in (data if isinstance(data, list) else [data]) if isinstance(x, dict) and "errors" not in x]

    def _pages(self, path: str, params) -> list[dict]:
        url = path if path.startswith(("http://", "https://")) else self.base + path
        out: list[dict] = []
        while url:
            r = self.s.get(url, params=params, timeout=self.timeout, allow_redirects=not self.uses_session)
            if self.uses_session and _signed_out(r):
                raise SessionExpired()
            r.raise_for_status()
            data = r.json()
            # Real Canvas sometimes puts nulls or error objects in lists; keep only records.
            out.extend(x for x in (data if isinstance(data, list) else [data]) if isinstance(x, dict) and "errors" not in x)
            url = r.links.get("next", {}).get("url")
            params = {}
        return out


DOC_EXT = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".txt"}


def _doc_link(url: str) -> bool:
    return Path(url.split("?")[0].split("#")[0]).suffix.lower() in DOC_EXT


_FILE_ID = re.compile(r"/files/(\d+)")


def _canvas_file_ids(html: str) -> list[int]:
    """Canvas files a page links to or embeds: links like /courses/1/files/456/download, and the
    data-api-endpoint Canvas puts on file links."""
    ids = []
    for attr in re.findall(r'(?:href|src|data-api-endpoint)\s*=\s*["\']([^"\']+)["\']', html or "", re.IGNORECASE):
        m = _FILE_ID.search(attr)
        if m and ("/courses/" in attr or "/api/v1/files/" in attr or attr.startswith("/files/")):
            ids.append(int(m.group(1)))
    return list(dict.fromkeys(ids))


def _doc_links(html: str, base: str) -> list[str]:
    """Links to documents outside Canvas (a PDF on an instructor's or publisher's site)."""
    out = []
    host = urlparse(base).netloc
    for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html or "", re.IGNORECASE):
        if href.startswith(("http://", "https://")) and urlparse(href).netloc != host and _doc_link(href):
            out.append(href)
    return list(dict.fromkeys(out))


def _signed_out(r: requests.Response) -> bool:
    """Canvas no longer accepts the session (as opposed to "you may not see this", which it also answers
    with 401, for example when an instructor hides a course's Files)."""
    if r.status_code in (302, 303):
        return "/login" in r.headers.get("Location", "")
    if r.status_code != 401:
        return False
    try:
        return (r.json() or {}).get("status") == "unauthenticated"
    except ValueError:
        return True


def _parse_time(value: str | None, tz: ZoneInfo) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(tz)


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\n{3,}", "\n\n", text).strip()
