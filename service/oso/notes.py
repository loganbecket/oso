"""Reading and writing vault notes: front matter, safe file names, course folder lookup."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from .config import Config

_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def read_front_matter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[m.end():].lstrip("\r\n")


def with_front_matter(data: dict, body: str) -> str:
    fm = yaml.safe_dump({k: v for k, v in data.items() if v is not None}, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm}\n---\n\n{body.lstrip()}"


def safe_name(name: str, limit: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    return name[:limit] or "untitled"


def course_dir(cfg: Config, code: str | None) -> Path:
    c = cfg.course_for(code)
    if c:
        return cfg.vault / "Courses" / c.folder
    return cfg.vault / "Inbox"


def guess_type(title: str, default: str = "reading") -> str:
    t = title.lower()
    if re.search(r"\b(lecture|slides|lec\b|week \d+)", t):
        return "lecture"
    if re.search(r"\b(homework|hw|problem set|pset|assignment|lab)\b", t):
        return "homework"
    if re.search(r"\b(exam|midterm|final|quiz)\b", t):
        return "exam"
    if re.search(r"\bsyllabus\b", t):
        return "syllabus"
    return default


def stamp() -> str:
    return datetime.now().isoformat(timespec="minutes")


def split_sections(body: str, max_chars: int = 2500) -> list[tuple[str, str]]:
    """(heading, text) pairs; long sections are split into pieces that keep the heading."""
    out: list[tuple[str, str]] = []
    pos = 0
    heading = ""
    for m in _HEADING.finditer(body):
        _emit(out, heading, body[pos:m.start()], max_chars)
        heading = m.group(2).strip()
        pos = m.end()
    _emit(out, heading, body[pos:], max_chars)
    return out


def _emit(out: list[tuple[str, str]], heading: str, text: str, max_chars: int) -> None:
    text = text.strip()
    while len(text) > max_chars:
        cut = text.rfind("\n\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        out.append((heading, text[:cut]))
        text = text[cut:].strip()
    if text:
        out.append((heading, text))
