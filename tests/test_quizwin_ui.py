"""Opens the real quiz window and clicks through a quiz. Skipped where no display is available."""

from pathlib import Path

import pytest

from oso import config as cfgmod
from oso import db, profile, quizwin
from oso.config import Config, Course


def test_window_steps_through_and_submits(tmp_path: Path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display")

    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    monkeypatch.setattr(cfgmod, "load", lambda path=None: cfg)
    real = db.connect
    monkeypatch.setattr(db, "connect", lambda *a, **k: real(tmp_path / "t.sqlite"))
    with db.connect() as conn:
        qid = profile.start_quiz(conn, cfg, "PHYS-110", [
            {"number": 1, "topic": "K", "type": "multiple_choice", "difficulty": "easy", "question": "Pick B", "choices": ["x", "y"], "answer": "B"},
            {"number": 2, "topic": "F", "type": "worked_problem", "difficulty": "hard", "question": "Solve it"},
        ], window=True)

    from tkinter import messagebox, ttk

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    seen = []

    def drive(root):
        def find(widget, kind, text=None):
            for w in widget.winfo_children():
                if isinstance(w, kind) and (text is None or w.cget("text") == text):
                    return w
                found = find(w, kind, text)
                if found is not None:
                    return found
            return None

        root.update()
        find(root, ttk.Radiobutton, "B. y").invoke()
        find(root, ttk.Button, "Next").invoke()
        root.update()
        box = find(root, tk.Text)
        seen.append(find(root, ttk.Label).cget("text"))
        find(root, ttk.Button, "Review and submit").invoke()
        root.update()
        seen.append(find(root, ttk.Label).cget("text"))
        root.destroy()

    monkeypatch.setattr(tk.Tk, "mainloop", lambda self, n=0: drive(self))
    quizwin.run(qid)
    import gc

    gc.collect()  # free the window's Tcl objects here, on the main thread; Tcl aborts if a later test's thread frees them
    assert seen == ["Question 2 of 2", "Answers submitted."]
    with db.connect() as conn:
        view = profile.grading_view(conn, cfg, qid)
    assert view["questions"][0]["graded_by_window"] == "right" and view["questions"][1]["response"] is None
