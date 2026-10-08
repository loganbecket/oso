from pathlib import Path

from oso import skillsync
from oso.config import Config


def setup(tmp_path: Path, monkeypatch, version: str = "v1"):
    ship = tmp_path / "ship"
    ship.mkdir(exist_ok=True)
    (ship / "oso-summarize.md").write_text(f"summarize {version}\n", encoding="utf-8")
    (ship / "oso-quiz.md").write_text(f"quiz {version}\n", encoding="utf-8")
    monkeypatch.setattr(skillsync, "SHIPPED", ship)
    return Config(vault=tmp_path / "vault"), tmp_path / "state"


def test_seed_quiet_update_keep_edit_and_conflict(tmp_path: Path, monkeypatch):
    cfg, st = setup(tmp_path, monkeypatch)
    assert skillsync.sync(cfg, st) == []
    summ, quiz = skillsync.vault_file(cfg, "oso-summarize"), skillsync.vault_file(cfg, "oso-quiz")
    assert summ.read_text() == "summarize v1\n"

    summ.write_bytes(b"summarize, my way\r\n")  # the student edits one command
    assert skillsync.sync(cfg, st) == []
    assert summ.read_text() == "summarize, my way\n"

    setup(tmp_path, monkeypatch, "v2")  # Oso ships new versions of both
    assert skillsync.sync(cfg, st) == ["oso-summarize"]
    assert quiz.read_text() == "quiz v2\n"  # untouched copy updated quietly
    assert summ.read_text() == "summarize, my way\n"  # edited copy kept
    assert skillsync.conflicts(st) == ["oso-summarize"]
    d = skillsync.describe(cfg, st)[0]
    assert (d["yours"], d["oso_new"], d["oso_previous"]) == ("summarize, my way\n", "summarize v2\n", "summarize v1\n")


def test_resolve_choices(tmp_path: Path, monkeypatch):
    cfg, st = setup(tmp_path, monkeypatch)
    skillsync.sync(cfg, st)
    summ = skillsync.vault_file(cfg, "oso-summarize")
    summ.write_text("mine")
    setup(tmp_path, monkeypatch, "v2")
    skillsync.sync(cfg, st)

    assert "your version" in skillsync.resolve(cfg, "oso-summarize", "mine", state=st)
    assert summ.read_text() == "mine" and skillsync.conflicts(st) == []
    assert skillsync.sync(cfg, st) == []  # not flagged again

    setup(tmp_path, monkeypatch, "v3")
    skillsync.sync(cfg, st)
    skillsync.resolve(cfg, "oso-summarize", "combined", "mine plus v3", state=st)
    assert summ.read_text() == "mine plus v3"

    setup(tmp_path, monkeypatch, "v4")
    skillsync.sync(cfg, st)
    skillsync.resolve(cfg, "oso-summarize", "oso", state=st)
    assert summ.read_text() == "summarize v4\n"
    assert skillsync.sync(cfg, st) == []


def test_reset_and_student_files(tmp_path: Path, monkeypatch):
    cfg, st = setup(tmp_path, monkeypatch)
    skillsync.sync(cfg, st)
    skillsync.vault_file(cfg, "oso-summarize").write_text("mine")
    skillsync.vault_file(cfg, "oso-quiz").write_text("mine too")
    own = skillsync.vault_file(cfg, "my-own-command")
    own.write_text("the student's own")

    assert "oso-summarize" in skillsync.reset(cfg, ["oso-summarize"], st)
    assert skillsync.vault_file(cfg, "oso-summarize").read_text() == "summarize v1\n"
    assert skillsync.vault_file(cfg, "oso-quiz").read_text() == "mine too"
    assert "no command named" in skillsync.reset(cfg, ["nope"], st)

    skillsync.reset(cfg, None, st)
    assert skillsync.vault_file(cfg, "oso-quiz").read_text() == "quiz v1\n"
    assert own.read_text() == "the student's own"


def test_instructions_seed_when_missing(tmp_path: Path, monkeypatch):
    cfg, st = setup(tmp_path, monkeypatch)
    assert skillsync.instructions(cfg, "oso-quiz", st) == "quiz v1\n"
    assert skillsync.vault_file(cfg, "oso-quiz").exists()


def test_every_plugin_skill_points_at_a_shipped_file():
    plugin = Path(__file__).parent.parent / "plugin" / "skills"
    names = set(skillsync.shipped())
    for d in plugin.iterdir():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        if d.name in ("oso-doctor", "oso-skill-updates"):
            assert "skill_instructions" not in text
        else:
            assert d.name in names and f"name `{d.name}`" in text


def test_plugin_skill_front_matter_has_no_angle_brackets():
    """The Claude app skips a skill whose description contains angle brackets (it reads them as XML tags)."""
    plugin = Path(__file__).parent.parent / "plugin" / "skills"
    for d in plugin.iterdir():
        head = (d / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        assert "<" not in head and ">" not in head, d.name


def test_plugin_version_matches_release():
    """The Claude app only updates an installed plugin when its version changes."""
    import json
    import tomllib
    root = Path(__file__).parent.parent
    plugin = json.loads((root / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    release = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert plugin["version"] == release
