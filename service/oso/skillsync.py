"""The instructions behind each Oso command, kept in the vault where the student can edit them.

Each plugin skill is a one-line pointer: it asks the `skill_instructions` tool for the text in
`Oso/Skills/<name>.md` and follows it. Oso ships its own version of every file with the service, and on
every sync compares three texts per skill: the vault copy, the version shipped now, and the version
shipped last time (the base).

- vault copy missing: write the shipped version
- vault copy unchanged since the base: replace it with the shipped version (a quiet update)
- vault copy edited, shipped version unchanged: keep the student's copy
- both changed (or no base is recorded for an edited copy): a conflict. The new version waits in the data folder, Today.md says so, and the student
  picks theirs, Oso's, or a combination through `resolve_skill`.

Files the student adds to `Oso/Skills/` that Oso does not ship are never touched.
"""

from __future__ import annotations

from pathlib import Path

from . import config as cfgmod
from .config import Config

SHIPPED = Path(__file__).parent / "skills"
VAULT_DIR = ("Oso", "Skills")


def _state(state: Path | None) -> Path:
    return state or cfgmod.data_dir() / "skills"


def shipped() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(SHIPPED.glob("*.md"))}


def vault_file(cfg: Config, name: str) -> Path:
    return cfg.vault.joinpath(*VAULT_DIR, f"{name}.md")


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _same(a: str | None, b: str | None) -> bool:
    """Equal apart from line endings and trailing space, which editors and Drive change freely."""
    if a is None or b is None:
        return a is b
    norm = lambda t: "\n".join(line.rstrip() for line in t.replace("\r\n", "\n").strip().split("\n"))  # noqa: E731
    return norm(a) == norm(b)


def sync(cfg: Config, state: Path | None = None) -> list[str]:
    """Bring the vault copies up to date. Returns the names of skills in conflict."""
    st = _state(state)
    conflicts = []
    for name, new in shipped().items():
        local_path = vault_file(cfg, name)
        local = _read(local_path)
        base_path, pending_path = st / "base" / f"{name}.md", st / "new" / f"{name}.md"
        base = _read(base_path)
        if local is None or _same(local, base) or _same(local, new):
            if not _same(local, new):
                _write(local_path, new)
            _write(base_path, new)
            pending_path.unlink(missing_ok=True)
        elif base is None or not _same(new, base):
            _write(pending_path, new)
            conflicts.append(name)
        else:
            pending_path.unlink(missing_ok=True)  # the student's own edit; nothing new from Oso
    return conflicts


def conflicts(state: Path | None = None) -> list[str]:
    d = _state(state) / "new"
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else []


def instructions(cfg: Config, name: str, state: Path | None = None) -> str:
    """The student's copy of a skill's instructions, seeded from the shipped version if missing."""
    local = _read(vault_file(cfg, name))
    if local is not None:
        return local
    ship = shipped().get(name)
    if ship is None:
        raise ValueError(f"no Oso skill named {name!r}")
    _write(vault_file(cfg, name), ship)
    _write(_state(state) / "base" / f"{name}.md", ship)
    return ship


def describe(cfg: Config, state: Path | None = None) -> list[dict]:
    """Every conflict with the three texts, so Claude can show the difference."""
    st = _state(state)
    return [
        {
            "name": name,
            "path": "/".join(VAULT_DIR) + f"/{name}.md",
            "yours": _read(vault_file(cfg, name)),
            "oso_new": _read(st / "new" / f"{name}.md"),
            "oso_previous": _read(st / "base" / f"{name}.md"),
        }
        for name in conflicts(st)
    ]


def resolve(cfg: Config, name: str, choice: str, text: str | None = None, state: Path | None = None) -> str:
    """choice: 'mine' keeps the student's copy, 'oso' takes the new version, 'combined' saves `text`."""
    st = _state(state)
    pending_path = st / "new" / f"{name}.md"
    new = _read(pending_path)
    if new is None:
        return f"{name} has no pending update."
    if choice == "oso":
        _write(vault_file(cfg, name), new)
    elif choice == "combined":
        if not text:
            return "A combined version needs its text."
        _write(vault_file(cfg, name), text)
    elif choice != "mine":
        return "Choice must be mine, oso, or combined."
    _write(st / "base" / f"{name}.md", new)
    pending_path.unlink()
    return f"Saved {'your version' if choice == 'mine' else 'the combined version' if choice == 'combined' else 'the new Oso version'} of {name}."


def reset(cfg: Config, names: list[str] | None = None, state: Path | None = None) -> str:
    """Put Oso's current version back for the named commands (all when none are named), discarding the
    student's edits to them. Files the student added that Oso does not ship are left alone."""
    st = _state(state)
    ship = shipped()
    unknown = [n for n in names or [] if n not in ship]
    if unknown:
        return f"Oso has no command named {', '.join(unknown)}."
    chosen = names or list(ship)
    for name in chosen:
        _write(vault_file(cfg, name), ship[name])
        _write(st / "base" / f"{name}.md", ship[name])
        (st / "new" / f"{name}.md").unlink(missing_ok=True)
    return f"Restored Oso's version of {'every command' if not names else ', '.join(chosen)}."
