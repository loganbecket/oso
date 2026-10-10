import pytest

from oso import config as cfgmod, saved_pages, sites
from oso.config import Config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(cfgmod, "config_path", lambda: path)
    monkeypatch.setattr(sites, "public_host", lambda host: not host.startswith("192.168."))
    return Config(vault=tmp_path)


def test_saved_pages_kept_in_settings(cfg):
    with pytest.raises(ValueError):
        saved_pages.save(cfg, "Dining hours", "dining.example.edu/hours", "")  # Claude needs to know what it's for
    with pytest.raises(ValueError):
        saved_pages.save(cfg, "Router", "http://192.168.1.1/", "the router")
    saved_pages.save(cfg, "Dining hours", "dining.example.edu/hours", "hours for every dining hall")
    saved_pages.save(cfg, "dining HOURS", "dining.example.edu/hours#today", "hours for every dining hall on campus")
    saved_pages.save(cfg, 'St. Mary\'s "events"', "https://stmarys.example.org/events", "my church's services and events")
    assert saved_pages.describe(cfg)[0] == {"name": "Dining hours", "about": "hours for every dining hall on campus",
                                            "url": "https://dining.example.edu/hours"}
    assert cfgmod.load().saved_pages == cfg.saved_pages
    assert saved_pages.forget(cfg, "dining hours") and not saved_pages.forget(cfg, "dining hours")
    assert [p.name for p in cfgmod.load().saved_pages] == ['St. Mary\'s "events"']


def test_saved_pages_are_listed_in_the_vault_instructions(cfg):
    saved_pages.save(cfg, "Dining hours", "dining.example.edu/hours", "menus and hours for every dining hall")
    text = (cfg.vault / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Saved pages" in text and "- **Dining hours**: menus and hours for every dining hall" in text and "`read_page`" in text
    saved_pages.forget(cfg, "Dining hours")
    assert "Saved pages" not in (cfg.vault / "CLAUDE.md").read_text(encoding="utf-8")
