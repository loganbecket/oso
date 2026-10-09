"""One writer for every note Oso puts in the vault: his notes and his edits are never overwritten."""

from pathlib import Path

from oso import notes, sites, skillsync, transcribe, vault, watch
from oso.config import Config, Course


def test_oso_notes_carry_a_marker_and_his_edits_stop_the_rewrite(tmp_path: Path):
    note = tmp_path / "02 Forces.md"
    assert vault.write_note(note, {"type": "textbook", "chapter": "Forces"}, "# Forces\n\nF = ma\n")
    fm, body = notes.read_front_matter(note.read_text(encoding="utf-8"))
    assert fm["oso"] == vault.body_hash(body) and vault.ownership(note) == "ours"
    assert not list(tmp_path.glob("*.oso-tmp"))
    assert vault.write_note(note, {"type": "textbook", "chapter": "Forces"}, "# Forces\n\nF = ma, revised\n")
    assert "revised" in note.read_text(encoding="utf-8")

    note.write_text(note.read_text(encoding="utf-8") + "\nMy own remark.\n", encoding="utf-8")
    assert vault.ownership(note) == "edited"
    assert not vault.write_note(note, {"type": "textbook", "chapter": "Forces"}, "# Forces\n\nthird version\n")
    assert "My own remark." in note.read_text(encoding="utf-8") and "third version" not in note.read_text(encoding="utf-8")


def test_his_own_notes_and_older_oso_notes(tmp_path: Path):
    his = tmp_path / "Week 2.md"
    his.write_text("---\ntype: notes\n---\n\nMy lecture notes.\n", encoding="utf-8")
    assert vault.ownership(his) == "theirs" and not vault.write_note(his, {"type": "notes"}, "replaced")
    assert "My lecture notes." in his.read_text(encoding="utf-8")

    old = tmp_path / "03 Energy.md"  # written by an Oso from before the marker existed
    old.write_text("---\ntype: textbook\nchapter: Energy\n---\n\n# Energy\n", encoding="utf-8")
    assert vault.ownership(old) == "theirs" and vault.ownership(old, vault.textbook_note) == "ours"
    assert vault.write_note(old, {"type": "textbook", "chapter": "Energy"}, "# Energy\n\nnew text\n", vault.textbook_note)
    assert vault.ownership(old) == "ours"  # it carries the marker from now on


def test_the_watcher_tells_his_changes_from_osos_by_the_marker(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    folder = cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Notes"
    folder.mkdir(parents=True)
    ours = folder / "Summary.md"
    vault.write_note(ours, {"type": "notes"}, "# Summary\n")
    assert watch.matters(cfg, ours) is False
    ours.write_text(ours.read_text(encoding="utf-8") + "\nhis line\n", encoding="utf-8")
    assert watch.matters(cfg, ours) is True  # once he edits it, it is his
    his = folder / "Week 2.md"
    his.write_text("# Week 2\n", encoding="utf-8")
    assert watch.matters(cfg, his) is True


def test_site_pages_with_the_same_title_get_their_own_notes():
    root = "https://faculty.example.edu/~lee/phys110/"
    a = sites._note_name(root, root, "PHYS 110 - Dr. Lee")
    b = sites._note_name(root, root + "week5.html", "PHYS 110 - Dr. Lee")
    c = sites._note_name(root, root + "week6.html", "PHYS 110 - Dr. Lee")
    assert a == "PHYS 110 - Dr. Lee.md" and b != c and b.startswith("PHYS 110 - Dr. Lee ") and b.endswith(".md")


def test_a_skill_that_cannot_be_read_right_now_is_left_alone(tmp_path: Path, monkeypatch):
    ship = tmp_path / "ship"
    ship.mkdir()
    (ship / "oso-quiz.md").write_text("quiz v2\n", encoding="utf-8")
    monkeypatch.setattr(skillsync, "SHIPPED", ship)
    cfg = Config(vault=tmp_path / "vault")
    local = skillsync.vault_file(cfg, "oso-quiz")
    local.parent.mkdir(parents=True)
    local.write_text("my edited quiz instructions\n", encoding="utf-8")
    real = skillsync._read

    def flaky(p: Path):
        if p == local:
            raise PermissionError("Drive is still fetching this file")
        return real(p)

    monkeypatch.setattr(skillsync, "_read", flaky)
    assert skillsync.sync(cfg, tmp_path / "state") == []
    assert local.read_text(encoding="utf-8") == "my edited quiz instructions\n"


def test_transcription_continues_beside_a_note_he_edited(tmp_path: Path):
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "Physics")])
    path = transcribe._note_path(cfg, "PHYS-110", "Lab notebook", "2026-10-05T14:00:00+00:00")
    path.parent.mkdir(parents=True)
    fm, body = transcribe._header(cfg, "PHYS-110", "Lab notebook")
    vault.write_note(path, fm, body)
    assert vault.ownership(path, vault.transcribed_note) == "ours"
    path.write_text(path.read_text(encoding="utf-8") + "\nI added this.\n", encoding="utf-8")
    assert vault.ownership(path, vault.transcribed_note) == "edited"
