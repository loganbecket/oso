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
            {"number": 1, "topic": "K", "type": "multiple_choice", "difficulty": "easy", "question": "Pick B", "choices": ["ex", "why"], "answer": "B"},
            {"number": 2, "topic": "F", "type": "worked_problem", "difficulty": "hard", "question": "Solve it", "criteria": "x = 2"},
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
        find(root, ttk.Radiobutton, "B. why").invoke()
        find(root, ttk.Radiobutton, "Sure").invoke()
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
    assert view["questions"][0]["confidence"] == "sure" and view["questions"][1]["confidence"] is None


def test_a_taken_quiz_opens_read_only_with_the_answers(tmp_path: Path, monkeypatch):
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
            {"number": 1, "topic": "K", "type": "multiple_choice", "difficulty": "easy", "question": "Pick B", "choices": ["ex", "why"], "answer": "B"},
            {"number": 2, "topic": "F", "type": "short_answer", "difficulty": "medium", "question": "Newton's second law?",
             "criteria": {"expected": "F = ma (net force)", "partial_credit": "F = ma without net"}},
        ], window=True)
        profile.window_submit(conn, qid, {1: {"response": "A", "seconds": 4, "changes": 0, "confidence": "sure"},
                                          2: {"response": "F = ma", "seconds": 20, "changes": 0}})
        profile.record_answers(conn, qid, [{"number": 2, "result": "partly_right", "mistake": "incomplete",
                                            "note": "It's the net force that equals ma."}])
        profile.finish_quiz(conn, qid)
        _, qs, _ = quizwin.review_data(conn, qid)
    assert qs[0]["result"] == "wrong" and qs[0]["key"] == "B" and qs[1]["expected"] == "F = ma (net force)"

    from tkinter import ttk

    seen = []

    def drive(root):
        def all_widgets(widget):
            for w in widget.winfo_children():
                yield w
                yield from all_widgets(w)

        root.update()
        radios = [w for w in all_widgets(root) if isinstance(w, tk.Radiobutton)]
        seen.append([(w.cget("text"), str(w.cget("state"))) for w in radios])
        seen.append([w.cget("text") for w in all_widgets(root) if isinstance(w, ttk.Label)])
        next(w for w in all_widgets(root) if isinstance(w, ttk.Button) and w.cget("text") == "Next").invoke()
        root.update()
        seen.append([w.cget("text") for w in all_widgets(root) if isinstance(w, ttk.Label)])
        next(w for w in all_widgets(root) if isinstance(w, ttk.Button) and w.cget("text") == "Close").invoke()

    monkeypatch.setattr(tk.Tk, "mainloop", lambda self, n=0: drive(self))
    quizwin.run(qid)  # submitted, so it opens for review, not to take again
    import gc

    gc.collect()
    assert seen[0] == [("A. ex   ✗ your answer", "disabled"), ("B. why   ✓ correct answer", "disabled")]
    assert "Wrong · how sure you were: Sure" in seen[1]
    assert "Correct answer: F = ma (net force)" in seen[2] and "Partly right" in seen[2] and "It's the net force that equals ma." in seen[2]
