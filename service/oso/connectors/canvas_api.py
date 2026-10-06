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
            try:
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
        title = a.get("name", "").strip()
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
        """Download course files and announcements into the vault. Safe to run on every check."""
        counts = {"files": 0, "announcements": 0}
        for course in self._courses():
            code = course.get("course_code") or str(course["id"])
            folder = notes.course_dir(self.cfg, code)
            if folder is None:
                continue  # course not set up in Oso yet
            counts["files"] += self._mirror_files(course["id"], folder / "Canvas")
            counts["announcements"] += self._mirror_announcements(course["id"], folder / "Announcements")
        return counts

    def _mirror_files(self, course_id: int, dest: Path) -> int:
        n = 0
        try:
            files = self._pages(f"/api/v1/courses/{course_id}/files", {"per_page": 100})
        except requests.HTTPError:
            return 0
        for f in files:
            if (f.get("size") or 0) > MAX_FILE_MB * 1024 * 1024 or f.get("locked_for_user"):
                continue
            name = notes.safe_name(f.get("display_name") or f.get("filename") or str(f["id"]), limit=120)
            target = dest / name
            stamp = _parse_time(f.get("updated_at"), self.tz)
            if target.exists() and stamp and target.stat().st_mtime >= stamp.timestamp():
                continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with self.s.get(f["url"], stream=True, timeout=self.timeout) as r:
                    r.raise_for_status()
                    with target.open("wb") as out:
                        for chunk in r.iter_content(1 << 16):
                            out.write(chunk)
                n += 1
            except requests.RequestException as e:
                log.warning("could not download %s: %s", name, type(e).__name__)
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
        url = self.base + path
        out: list[dict] = []
        while url:
            r = self.s.get(url, params=params, timeout=self.timeout, allow_redirects=not self.uses_session)
            if self.uses_session and (r.status_code in (401, 302, 303) or "/login" in r.headers.get("Location", "")):
                raise SessionExpired()
            r.raise_for_status()
            data = r.json()
            out.extend(data if isinstance(data, list) else [data])
            url = r.links.get("next", {}).get("url")
            params = {}
        return out


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
