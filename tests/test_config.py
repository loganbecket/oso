"""The settings file: odd values round-trip, a broken file is a sentence, and the command line never shows a trace."""

from pathlib import Path

import pytest

from oso import cli, config as cfgmod, sync
from oso.config import Config, Course


def test_odd_values_round_trip(tmp_path: Path):
    cfg = Config(vault=tmp_path / 'my "vault"', timezone='Europe/"Oslo"', quiet_hours='22:00-07:00"',
                 courses=[Course('PHYS-110', 'Physics: "Mechanics"\nand more\ttabs', '2026 Fall/Physics')],
                 muted_senders=['no"reply@x.edu'])
    path = tmp_path / "config.toml"
    cfgmod.save(cfg, path)
    back = cfgmod.load(path)
    assert back.vault == cfg.vault and back.timezone == cfg.timezone and back.quiet_hours == cfg.quiet_hours
    assert back.courses[0].name == cfg.courses[0].name and back.muted_senders == cfg.muted_senders


def test_a_broken_settings_file_is_a_sentence_not_a_trace(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('vault = "x"\ntimezone = "unterminated\n', encoding="utf-8")
    with pytest.raises(cfgmod.ConfigError) as e:
        cfgmod.load(path)
    assert "settings file could not be read" in str(e.value)


def test_command_line_failures_are_one_sentence(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(cfgmod, "data_dir", lambda: tmp_path)

    def boom(args):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(cli, "_dispatch", boom)
    assert cli.main(["sync"]) == 1
    err = capsys.readouterr().err
    assert "Oso couldn't finish 'sync'" in err and "Traceback" not in err
    assert "Traceback" in (tmp_path / "errors.log").read_text(encoding="utf-8")
    assert sync is not None
