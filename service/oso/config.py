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
    sites: list[str] = field(default_factory=list)  # instructor web pages followed for new materials (sites.py)

    @property
    def folder_name(self) -> str:
        """The last part of the folder, which is what the tablet and clip filing match on."""
        return Path(self.folder).name


@dataclass
class SavedPage:
    name: str  # what he calls it: "Dining hours"
    url: str
    about: str  # what it's for, so Claude knows when to look at it: "hours for every dining hall on campus"


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
    background_model: str = "sonnet"  # Claude model that acts on his rules and reads school email and GroupMe in the background
    read_cap_chars: int = 12000  # read_note returns at most this many characters per call; 0 = no cap
    write_vault_instructions: bool = True  # keep a CLAUDE.md at the vault root for Claude Code sessions
    channel: str = "stable"  # stable (newest tagged version) or latest (master)
    installed_version: str | None = None  # tag or short commit of the installed service
    strong_percent: int = 95  # a topic is strong at this weighted accuracy or better...
    strong_min_results: int = 6  # ...over at least this many results in the last 60 days
    untested_below: int = 3  # fewer results than this and a topic counts as untested
    half_life_days: int = 21  # a result this old counts half as much as one from today
    readiness_days: int = 7  # exams this close get readiness checks in Today.md
    quiz_warning_percent: int = 70  # a last quiz below this on an exam's topics is flagged
    canvas_notify: bool = True  # show a desktop notification when the Canvas sign-in expires
    auto_read: bool = True  # have Claude read handwriting, equations, tables, and drawings in the background
    auto_read_per_day: int = 0  # optional daily limit on those pages (0 = no limit)
    backup_folder: str | None = None  # where the nightly backup goes (a NAS share, a drive); none = no backup
    backup_hour: int = 2  # the backup runs on the first check after this hour each day
    site_check_hours: int = 6  # how often instructors' websites are checked for new materials
    muted_senders: list[str] = field(default_factory=list)  # email addresses, @domains, or mailing lists never read
    muted_groups: list[str] = field(default_factory=list)  # GroupMe group ids (or names) never read
    message_reads_per_day: int = 0  # optional daily limit on messages Claude reads (0 = no limit)
    saved_pages: list[SavedPage] = field(default_factory=list)  # web pages read live when he asks (saved_pages.py)

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

    def resolve(self, ref: str | None) -> Course | None:
        """The course a code, a name, a folder name, or Canvas's own label ("PHYS 110", "PHYS-110-001") refers
        to, whatever the case, spacing, or punctuation. None when nothing matches."""
        if not ref:
            return None
        key = _course_key(ref)
        if not key:
            return None
        for c in self.courses:
            if _course_key(c.code) == key:
                return c
        for c in self.courses:
            if key in (_course_key(c.name), _course_key(c.folder_name)):
                return c
        for c in self.courses:  # "PHYS-110-001" or "2026FA PHYS 110" names PHYS-110
            ck = _course_key(c.code)
            if ck and (key.startswith(ck) or key.endswith(ck)) and len(ck) >= 5:
                return c
        return None

    def finished_codes(self) -> set[str]:
        return {c.code.lower() for c in self.courses if c.finished}

    def is_active(self, code: str | None) -> bool:
        """False only for a course marked finished; items with no or unknown course stay visible."""
        return (code or "").lower() not in self.finished_codes()


def _course_key(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


class ConfigError(Exception):
    pass


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        raise ConfigError(
            f"Oso is not set up yet. Run 'oso init --vault <path to your Obsidian vault>'. "
            f"(Looked for {path})"
        )
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise ConfigError(f"Oso's settings file could not be read ({path}). Run 'oso settings' to set it up again, "
                          f"or fix the line it mentions: {str(e).splitlines()[0][:120]}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"Oso's settings file could not be read ({path}).")
    try:
        vault = Path(raw["vault"]).expanduser()
    except KeyError as e:
        raise ConfigError(f"{path} is missing the 'vault' setting") from e
    courses = [
        Course(code=c["code"], name=c.get("name", c["code"]), folder=c.get("folder", c.get("name", c["code"])),
               drive_folder=c.get("drive_folder") or None, term=c.get("term") or None,
               finished=bool(c.get("finished", False)), related=[str(x) for x in c.get("related", [])],
               sites=[str(x) for x in c.get("sites", [])])
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
        background_model=str(raw.get("background_model", "sonnet")),
        read_cap_chars=int(raw.get("read_cap_chars", 12000)),
        write_vault_instructions=bool(raw.get("write_vault_instructions", True)),
        channel=str(raw.get("channel", "stable")),
        installed_version=raw.get("installed_version") or None,
        strong_percent=_strong_percent(raw),
        strong_min_results=int(raw.get("strong_min_results", 6)),
        untested_below=int(raw.get("untested_below", 3)),
        half_life_days=int(raw.get("half_life_days", 21)),
        readiness_days=int(raw.get("readiness_days", 7)),
        quiz_warning_percent=int(raw.get("quiz_warning_percent", 70)),
        canvas_notify=bool(raw.get("canvas_notify", True)),
        auto_read=bool(raw.get("auto_read", True)),
        auto_read_per_day=int(raw.get("auto_read_per_day", 0)),
        backup_folder=raw.get("backup_folder") or None,
        backup_hour=int(raw.get("backup_hour", 2)),
        site_check_hours=int(raw.get("site_check_hours", 6)),
        muted_senders=[str(x) for x in raw.get("muted_senders", [])],
        muted_groups=[str(x) for x in raw.get("muted_groups", [])],
        message_reads_per_day=int(raw.get("message_reads_per_day", 0)),
        saved_pages=[SavedPage(name=str(p["name"]), url=str(p["url"]), about=str(p.get("about", "")))
                     for p in raw.get("saved_pages", []) if isinstance(p, dict) and p.get("name") and p.get("url")],
    )


# Raised when a default changes in a way that should reach settings saved under the old default.
SETTINGS_VERSION = 2


def _strong_percent(raw: dict) -> int:
    value = int(raw.get("strong_percent", 95))
    if int(raw.get("settings_version", 1)) < 2 and value == 80:  # the old default; 80% was too easy to call strong
        return 95
    return value


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Oso configuration. Secrets are not stored here.",
        f"settings_version = {SETTINGS_VERSION}",
        f'vault = "{_toml_str(str(cfg.vault))}"',
        f'timezone = "{_toml_str(cfg.timezone)}"',
        f'quiet_hours = "{_toml_str(cfg.quiet_hours)}"' if cfg.quiet_hours else '# quiet_hours = "22:00-07:00"',
        "muted_courses = [" + ", ".join(f'"{_toml_str(c)}"' for c in cfg.muted_courses) + "]",
        f'remarkable_folder = "{_toml_str(cfg.remarkable_folder)}"' if cfg.remarkable_folder else '# remarkable_folder = "School"',
        f"sync_interval_minutes = {cfg.sync_interval_minutes}",
        f"urgent_days = {cfg.urgent_days}",
        f"stale_hours = {cfg.stale_hours}",
        f"render_height_px = {cfg.render_height_px}",
        f'transcribe_model = "{_toml_str(cfg.transcribe_model)}"',
        f'exam_model = "{_toml_str(cfg.exam_model)}"',
        f'background_model = "{_toml_str(cfg.background_model)}"',
        f"read_cap_chars = {cfg.read_cap_chars}",
        f"write_vault_instructions = {'true' if cfg.write_vault_instructions else 'false'}",
        f'channel = "{_toml_str(cfg.channel)}"',
        *([f'installed_version = "{_toml_str(cfg.installed_version)}"'] if cfg.installed_version else []),
        f"strong_percent = {cfg.strong_percent}",
        f"strong_min_results = {cfg.strong_min_results}",
        f"untested_below = {cfg.untested_below}",
        f"half_life_days = {cfg.half_life_days}",
        f"readiness_days = {cfg.readiness_days}",
        f"quiz_warning_percent = {cfg.quiz_warning_percent}",
        f"canvas_notify = {'true' if cfg.canvas_notify else 'false'}",
        f"auto_read = {'true' if cfg.auto_read else 'false'}",
        f"auto_read_per_day = {cfg.auto_read_per_day}",
        *([f'backup_folder = "{_toml_str(cfg.backup_folder)}"'] if cfg.backup_folder else []),
        f"backup_hour = {cfg.backup_hour}",
        f"site_check_hours = {cfg.site_check_hours}",
        "muted_senders = [" + ", ".join(f'"{_toml_str(x)}"' for x in cfg.muted_senders) + "]",
        "muted_groups = [" + ", ".join(f'"{_toml_str(x)}"' for x in cfg.muted_groups) + "]",
        f"message_reads_per_day = {cfg.message_reads_per_day}",
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
            *(["sites = [" + ", ".join(f'"{_toml_str(u)}"' for u in c.sites) + "]"] if c.sites else []),
            "",
        ]
    for p in cfg.saved_pages:
        lines += ["[[saved_pages]]", f'name = "{_toml_str(p.name)}"', f'url = "{_toml_str(p.url)}"', f'about = "{_toml_str(p.about)}"', ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _toml_str(s: str) -> str:
    """Escape a value for a basic TOML string: backslashes, quotes, and control characters (a newline in a
    course name must not break the file)."""
    out = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return "".join(f"\\u{ord(ch):04X}" if ord(ch) < 0x20 or ch == "\x7f" else ch for ch in out)
