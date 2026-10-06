"""Configuration: one TOML file in the user's config directory.

Secrets never go here; see secrets.py.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from platformdirs import user_config_dir, user_data_dir

APP = "oso"


def config_path() -> Path:
    return Path(user_config_dir(APP)) / "config.toml"


def data_dir() -> Path:
    p = Path(user_data_dir(APP))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Course:
    code: str
    name: str
    folder: str  # path under Courses/, normally "<term>/<name>", e.g. "2026 Fall/Calculus II"
    drive_folder: str | None = None  # a local path synced by Google Drive for Desktop, mirrored into the course folder
    term: str | None = None  # e.g. "2026 Fall"
    finished: bool = False  # out of the briefing, deadlines, alerts, and default search; still searchable by name
    related: list[str] = field(default_factory=list)  # codes of earlier courses whose notes this course's searches include

    @property
    def folder_name(self) -> str:
        """The last part of the folder, which is what the tablet and clip filing match on."""
        return Path(self.folder).name


@dataclass
class Config:
    vault: Path
    timezone: str = "America/New_York"
    courses: list[Course] = field(default_factory=list)
    quiet_hours: str | None = None  # "22:00-07:00": alerts wait until the end of the window
    muted_courses: list[str] = field(default_factory=list)
    remarkable_folder: str | None = None  # optional tablet folder that holds the course folders; None = tablet root
    sync_interval_minutes: int = 15  # how often the watcher runs
    urgent_days: int = 7  # a new or moved item due within this many days counts as urgent
    stale_hours: int = 24  # a source with no successful sync for this long is called out
    render_height_px: int = 1200  # height of page images sent for transcription
    transcribe_model: str = "sonnet"  # Claude model for reading handwriting
    exam_model: str = "opus"  # Claude model for study guides and practice tests
    read_cap_chars: int = 12000  # read_note returns at most this many characters per call; 0 = no cap
    write_vault_instructions: bool = True  # keep a CLAUDE.md at the vault root for Claude Code sessions
    repo: str = "loganbecket/oso"  # GitHub repository Oso installs and updates from
    channel: str = "stable"  # stable (newest tagged version) or latest (master)
    installed_version: str | None = None  # tag or short commit of the installed service
    strong_percent: int = 80  # a topic is strong at this weighted accuracy or better...
    strong_min_results: int = 6  # ...over at least this many results in the last 60 days
    untested_below: int = 3  # fewer results than this and a topic counts as untested
    half_life_days: int = 21  # a result this old counts half as much as one from today
    readiness_days: int = 7  # exams this close get readiness checks in Today.md
    quiz_warning_percent: int = 70  # a last quiz below this on an exam's topics is flagged

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def course_for(self, code: str | None) -> Course | None:
        if not code:
            return None
        code = code.strip().lower()
        for c in self.courses:
            if c.code.lower() == code:
                return c
        return None

    def finished_codes(self) -> set[str]:
        return {c.code.lower() for c in self.courses if c.finished}

    def is_active(self, code: str | None) -> bool:
        """False only for a course marked finished; items with no or unknown course stay visible."""
        return (code or "").lower() not in self.finished_codes()


class ConfigError(Exception):
    pass


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(
            f"Oso is not set up yet. Run 'oso init --vault <path to your Obsidian vault>'. "
            f"(Looked for {path})"
        )
    with path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        vault = Path(raw["vault"]).expanduser()
    except KeyError as e:
        raise ConfigError(f"{path} is missing the 'vault' setting") from e
    courses = [
        Course(code=c["code"], name=c.get("name", c["code"]), folder=c.get("folder", c.get("name", c["code"])),
               drive_folder=c.get("drive_folder") or None, term=c.get("term") or None,
               finished=bool(c.get("finished", False)), related=[str(x) for x in c.get("related", [])])
        for c in raw.get("courses", [])
    ]
    return Config(
        vault=vault,
        timezone=raw.get("timezone", "America/New_York"),
        courses=courses,
        quiet_hours=raw.get("quiet_hours") or None,
        muted_courses=[str(c) for c in raw.get("muted_courses", [])],
        remarkable_folder=raw.get("remarkable_folder") or None,
        sync_interval_minutes=int(raw.get("sync_interval_minutes", 15)),
        urgent_days=int(raw.get("urgent_days", 7)),
        stale_hours=int(raw.get("stale_hours", 24)),
        render_height_px=int(raw.get("render_height_px", 1200)),
        transcribe_model=str(raw.get("transcribe_model", "sonnet")),
        exam_model=str(raw.get("exam_model", "opus")),
        read_cap_chars=int(raw.get("read_cap_chars", 12000)),
        write_vault_instructions=bool(raw.get("write_vault_instructions", True)),
        repo=str(raw.get("repo", "loganbecket/oso")),
        channel=str(raw.get("channel", "stable")),
        installed_version=raw.get("installed_version") or None,
        strong_percent=int(raw.get("strong_percent", 80)),
        strong_min_results=int(raw.get("strong_min_results", 6)),
        untested_below=int(raw.get("untested_below", 3)),
        half_life_days=int(raw.get("half_life_days", 21)),
        readiness_days=int(raw.get("readiness_days", 7)),
        quiz_warning_percent=int(raw.get("quiz_warning_percent", 70)),
    )


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Oso configuration. Secrets are not stored here.",
        f'vault = "{_toml_str(str(cfg.vault))}"',
        f'timezone = "{cfg.timezone}"',
        f'quiet_hours = "{cfg.quiet_hours}"' if cfg.quiet_hours else '# quiet_hours = "22:00-07:00"',
        "muted_courses = [" + ", ".join(f'"{_toml_str(c)}"' for c in cfg.muted_courses) + "]",
        f'remarkable_folder = "{_toml_str(cfg.remarkable_folder)}"' if cfg.remarkable_folder else '# remarkable_folder = "School"',
        f"sync_interval_minutes = {cfg.sync_interval_minutes}",
        f"urgent_days = {cfg.urgent_days}",
        f"stale_hours = {cfg.stale_hours}",
        f"render_height_px = {cfg.render_height_px}",
        f'transcribe_model = "{_toml_str(cfg.transcribe_model)}"',
        f'exam_model = "{_toml_str(cfg.exam_model)}"',
        f"read_cap_chars = {cfg.read_cap_chars}",
        f"write_vault_instructions = {'true' if cfg.write_vault_instructions else 'false'}",
        f'repo = "{_toml_str(cfg.repo)}"',
        f'channel = "{_toml_str(cfg.channel)}"',
        *([f'installed_version = "{_toml_str(cfg.installed_version)}"'] if cfg.installed_version else []),
        f"strong_percent = {cfg.strong_percent}",
        f"strong_min_results = {cfg.strong_min_results}",
        f"untested_below = {cfg.untested_below}",
        f"half_life_days = {cfg.half_life_days}",
        f"readiness_days = {cfg.readiness_days}",
        f"quiz_warning_percent = {cfg.quiz_warning_percent}",
        "",
    ]
    for c in cfg.courses:
        lines += [
            "[[courses]]",
            f'code = "{_toml_str(c.code)}"',
            f'name = "{_toml_str(c.name)}"',
            f'folder = "{_toml_str(c.folder)}"',
            *([f'drive_folder = "{_toml_str(c.drive_folder)}"'] if c.drive_folder else []),
            *([f'term = "{_toml_str(c.term)}"'] if c.term else []),
            *(["finished = true"] if c.finished else []),
            *(["related = [" + ", ".join(f'"{_toml_str(r)}"' for r in c.related) + "]"] if c.related else []),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
