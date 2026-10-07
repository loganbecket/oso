import os
from pathlib import Path

import numpy as np
import pytest

from oso import search
from oso.config import Config, Course

# A stand-in for the embedding model: words that mean the same thing share a dimension.
SYNONYMS = {"derivative": 0, "rate": 0, "slope": 0, "integral": 1, "area": 1, "accumulation": 1, "photosynthesis": 2, "chlorophyll": 2}


def fake_vec(text: str):
    v = np.zeros(search.DIM, dtype=np.float32)
    for w in text.lower().replace(".", " ").replace("?", " ").split():
        if w in SYNONYMS:
            v[SYNONYMS[w]] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(search, "embed_passages", lambda texts: [fake_vec(t).tobytes() for t in texts])
    monkeypatch.setattr(search, "embed_query", fake_vec)


def vault(tmp_path: Path) -> Config:
    cfg = Config(vault=tmp_path / "vault", courses=[Course("MATH-101", "Calculus", "Calculus"), Course("BIO-110", "Biology", "Biology")])
    notes = cfg.vault / "Courses" / "Calculus" / "Notes"
    notes.mkdir(parents=True)
    (notes / "Week 2.md").write_text("---\ntype: notes\n---\n\n# Slopes\n\nThe rate of change at a point is the slope of the tangent line.\n\n# Areas\n\nAccumulation under a curve gives the area.\n")
    bio = cfg.vault / "Courses" / "Biology" / "Notes"
    bio.mkdir(parents=True)
    (bio / "Plants.md").write_text("# Light\n\nChlorophyll absorbs light.\n")
    (cfg.vault / "Courses" / "Calculus" / "Handwriting").mkdir()
    (cfg.vault / "Courses" / "Calculus" / "Handwriting" / "raw.md").write_text("derivative derivative")
    return cfg


def test_meaning_finds_sections_without_the_word(tmp_path: Path, fake_model):
    cfg = vault(tmp_path)
    db = tmp_path / "s.sqlite"
    assert search.update(cfg, db) == {"indexed": 2, "removed": 0, "embedded": 3}
    hits = search.query(cfg, "what is a derivative", path=db)
    assert hits[0]["heading"] == "Slopes" and hits[0]["course"] == "MATH-101"
    assert "tangent line" in hits[0]["text"]
    assert not any("Handwriting" in h["path"] for h in hits)
    assert [h["heading"] for h in search.query(cfg, "chlorophyll", course="BIO-110", path=db)] == ["Light"]
    assert all(h["course"] == "MATH-101" for h in search.query(cfg, "area", course="MATH-101", path=db))


def test_incremental_update_and_removal(tmp_path: Path, fake_model):
    cfg = vault(tmp_path)
    db = tmp_path / "s.sqlite"
    search.update(cfg, db)
    assert search.update(cfg, db) == {"indexed": 0, "removed": 0, "embedded": 0}
    (cfg.vault / "Courses" / "Biology" / "Notes" / "Plants.md").unlink()
    (cfg.vault / "Courses" / "Calculus" / "Notes" / "Week 2.md").write_text("# Integrals\n\nThe integral is accumulation.\n")
    assert search.update(cfg, db) == {"indexed": 1, "removed": 1, "embedded": 1}
    assert search.status(db) == {"notes": 1, "sections": 1, "without_meaning": 0}
    assert not any("Biology" in h["path"] for h in search.query(cfg, "photosynthesis chlorophyll", path=db))


def test_exact_words_without_the_model(tmp_path: Path, monkeypatch):
    cfg = vault(tmp_path)
    db = tmp_path / "s.sqlite"
    monkeypatch.setattr(search, "embed_passages", lambda texts: None)
    monkeypatch.setattr(search, "embed_query", lambda text: None)
    assert search.update(cfg, db)["embedded"] == 0
    assert search.status(db)["without_meaning"] == 3
    assert search.query(cfg, "tangent", path=db)[0]["heading"] == "Slopes"
    monkeypatch.setattr(search, "embed_passages", lambda texts: [fake_vec(t).tobytes() for t in texts])
    assert search.update(cfg, db)["embedded"] == 3  # filled in once the model is back


@pytest.mark.skipif(not os.environ.get("OSO_REAL_SEARCH_MODEL"), reason="downloads the real model")
def test_real_model(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(search.cfgmod, "data_dir", lambda: tmp_path)
    cached = os.environ.get("OSO_MODEL_CACHE")
    if cached and Path(cached).expanduser().is_dir():  # the release check's cached download, so it isn't fetched every time
        import shutil

        shutil.copytree(Path(cached).expanduser(), tmp_path / "models")
    cfg = vault(tmp_path)
    db = tmp_path / "s.sqlite"
    assert search.update(cfg, db)["embedded"] == 3
    assert search.query(cfg, "how fast is the function changing", path=db)[0]["heading"] == "Slopes"
