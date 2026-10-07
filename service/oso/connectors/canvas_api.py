"""Canvas REST API, read with the student's own signed-in session (canvas_session.py) or, where a
school allows one, an access token.

Adds what the calendar feed cannot: grade weights, points, submissions and grades, late and missing
flags, instructor comments, current course grades, announcements, and the course files, which are
mirrored into the vault. `fetch` gathers it all in one pass; `canvas_store.save` keeps it in the database.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
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
        )

    # ---- vault mirroring ---------------------------------------------------------------------

    def mirror(self) -> dict[str, int]:
        """Download course materials into the vault: everything linked in the course's modules (where most
        instructors put their files), the Files section, and announcements. Safe to run on every check."""
        counts = {"files": 0, "module_files": 0, "module_pages": 0, "announcements": 0}
        self.new_files: list[tuple[str, str]] = []  # (course code, plain description) for Today.md
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
            counts["announcements"] += self._mirror_announcements(course["id"], folder / "Announcements")
        return counts

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
                    path = self._module_page(course_id, item["page_url"], folder, title)
                    counts["pages"] += path is not None and path[1]
                    index.append(f"- [[{path[0]}|{title}]]" if path else f"- {title} (locked or unavailable)")
                elif kind == "ExternalUrl" and item.get("external_url"):
                    url = item["external_url"]
                    if _doc_link(url):
                        got = self._download(url, folder / notes.safe_name(Path(url.split("?")[0]).name, limit=120))
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

    def _module_page(self, course_id: int, page_url: str, folder: Path, title: str):
        try:
            pages = self._pages(f"/api/v1/courses/{course_id}/pages/{page_url}", {})
        except requests.HTTPError:
            return None
        if not pages or pages[0].get("locked_for_user"):
            return None
        page = pages[0]
        target = folder / f"{notes.safe_name(page.get('title') or title or page_url)[:80]}.md"
        fm = {"type": "canvas-page", "updated": page.get("updated_at"), "source": page.get("html_url")}
        text = notes.with_front_matter(fm, f"# {page.get('title') or title}\n\n{_strip_html(page.get('body') or '')}\n")
        changed = not target.exists() or target.read_text(encoding="utf-8") != text
        if changed:
            folder.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return (target.relative_to(self.cfg.vault).with_suffix("").as_posix(), changed)

    def _download(self, url: str, target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        try:
            with self.s.get(url, stream=True, timeout=self.timeout) as r:
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

    def _mirror_announcements(self, course_id: int, dest: Path) -> int:
        n = 0
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
        return n

    # ---- http --------------------------------------------------------------------------------

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
