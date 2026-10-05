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
    folder: str
    drive_folder: str | None = None  # a local path synced by Google Drive for Desktop, mirrored into the course folder


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
               drive_folder=c.get("drive_folder") or None)
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
        "",
    ]
    for c in cfg.courses:
        lines += [
            "[[courses]]",
            f'code = "{_toml_str(c.code)}"',
            f'name = "{_toml_str(c.name)}"',
            f'folder = "{_toml_str(c.folder)}"',
            *([f'drive_folder = "{_toml_str(c.drive_folder)}"'] if c.drive_folder else []),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
