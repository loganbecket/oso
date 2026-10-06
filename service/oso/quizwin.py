"""The quiz window: quizzes taken outside the chat, timed per question, answers hidden until submitted.

Claude writes a quiz in Cowork and records it with `start_quiz`; Oso then opens this window on the
student's computer (Oso's tools run there, so they can). One question at a time, with a timer that runs
only while a question is on screen. On submit, multiple choice is graded against the key Claude supplied,
typed answers are saved, and the student can attach written work: pages pulled from the reMarkable over
USB, or a scan or photo file. Each page carries the question number in its top corner; Claude matches
pages to questions when it grades.

The logic is in `QuizSession` (no window, so it can be tested); `run` wraps it in a tkinter window.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import config as cfgmod
from . import db, notes, profile
from .config import Config

IMAGE_EXT = {".png", ".jpg", ".jpeg"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class QuizSession:
    """One sitting of one quiz: which question is showing, the answers so far, and time per question."""

    def __init__(self, questions: list[dict], clock=time.monotonic, wall=_now):
        self.questions = questions
        self.clock, self.wall = clock, wall
        self.index = 0
        self.answers: dict[int, str | None] = {q["number"]: None for q in questions}
        self.seconds: dict[int, float] = {q["number"]: 0.0 for q in questions}
        self.changes: dict[int, int] = {q["number"]: 0 for q in questions}
        self.first_at: dict[int, str | None] = {q["number"]: None for q in questions}
        self._shown_at = clock()

    @property
    def current(self) -> dict:
        return self.questions[self.index]

    def _bank_time(self) -> None:
        t = self.clock()
        self.seconds[self.current["number"]] += t - self._shown_at
        self._shown_at = t

    def go(self, index: int) -> None:
        if 0 <= index < len(self.questions) and index != self.index:
            self._bank_time()
            self.index = index

    def answer(self, value: str | None) -> None:
        """Set the current question's answer. Changing an answer already given counts as a change."""
        n = self.current["number"]
        value = (value or "").strip() or None
        old = self.answers[n]
        if value == old:
            return
        if old is not None:
            self.changes[n] += 1
        if value is not None and self.first_at[n] is None:
            self.first_at[n] = self.wall()
        self.answers[n] = value

    def unanswered(self) -> list[int]:
        return [n for n, a in self.answers.items() if a is None]

    def responses(self) -> dict[int, dict]:
        self._bank_time()
        return {n: {"response": self.answers[n], "seconds": self.seconds[n], "changes": self.changes[n],
                    "first_answer_at": self.first_at[n]} for n in self.answers}


def load_questions(conn, quiz_id: int) -> tuple[dict, list[dict]]:
    profile.ensure(conn)
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise profile.ProfileError(f"There is no quiz {quiz_id}.")
    qs = []
    for r in conn.execute("SELECT number, question, qtype, choices FROM quiz_questions WHERE quiz_id = ? ORDER BY number", (quiz_id,)):
        qs.append({"number": r["number"], "question": r["question"] or "", "type": r["qtype"],
                   "choices": json.loads(r["choices"]) if r["choices"] else []})
    return dict(quiz), qs


def work_folder(cfg: Config, quiz: dict) -> Path:
    c = cfg.course_for(quiz["course"])
    base = cfg.vault / "Courses" / c.folder if c else cfg.vault / "Oso"
    return base / "Quizzes" / f"Quiz {quiz['id']}"


def import_work(conn, cfg: Config, quiz: dict, sources: list[Path], origin: str) -> int:
    """Copy written work into the quiz's folder, render PDFs to one image per page, and attach the pages."""
    folder = work_folder(cfg, quiz)
    pages_dir = folder / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    existing = len([p for p in pages_dir.iterdir() if p.is_file()])
    added: list[str] = []
    for src in sources:
        dest = folder / notes.safe_name(src.name)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        if dest.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(str(dest))
            for i in range(len(doc)):
                existing += 1
                out = pages_dir / f"page {existing:02d}.png"
                page = doc[i]
                scale = max(0.5, min(4.0, cfg.render_height_px / (page.get_height() or 1)))
                page.render(scale=scale).to_pil().save(out)
                added.append(out.relative_to(cfg.vault).as_posix())
        elif dest.suffix.lower() in IMAGE_EXT:
            existing += 1
            out = pages_dir / f"page {existing:02d}{dest.suffix.lower()}"
            shutil.copy2(dest, out)
            added.append(out.relative_to(cfg.vault).as_posix())
    return profile.add_work(conn, quiz["id"], added, origin)


def tablet_notebooks(cfg: Config) -> list[dict]:
    """Notebooks on the plugged-in tablet, most recently changed first; empty if it is not connected."""
    from .connectors.remarkable_usb import RemarkableUsb

    tab = RemarkableUsb(cfg)
    if not tab.connected():
        return []
    docs = [d for d in tab._walk() if d.get("Type") == "DocumentType" and d.get("fileType") in (None, "", "notebook")]
    return sorted(docs, key=lambda d: d.get("ModifiedClient") or "", reverse=True)


def pull_from_tablet(conn, cfg: Config, quiz: dict, doc: dict) -> int:
    from .connectors.remarkable_usb import RemarkableUsb

    folder = work_folder(cfg, quiz)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{notes.safe_name(doc.get('VissibleName') or doc['ID'])}.pdf"
    RemarkableUsb(cfg)._download(doc["ID"], target)
    return import_work(conn, cfg, quiz, [target], "tablet")


# ---- launching ------------------------------------------------------------------------------------


def launch(quiz_id: int) -> None:
    """Open the window in its own process, so the tool call that asked for it returns at once."""
    exe = Path(sys.executable)
    if sys.platform == "win32" and (exe.parent / "pythonw.exe").exists():
        exe = exe.parent / "pythonw.exe"  # no console window behind the quiz
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(exe), "-m", "oso.quizwin", str(quiz_id)], **kwargs)


# ---- the window -------------------------------------------------------------------------------------


def run(quiz_id: int) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    cfg = cfgmod.load()
    with db.connect() as conn:
        quiz, questions = load_questions(conn, quiz_id)
    c = cfg.course_for(quiz["course"])
    title = f"Oso quiz: {c.name if c else quiz['course']}"

    root = tk.Tk()
    root.title(title)
    root.geometry("760x560")
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)

    if quiz["submitted_at"]:
        ttk.Label(frm, text="This quiz has already been submitted. Go back to the chat and ask Claude to grade it.",
                  wraplength=700).pack(anchor="w")
        ttk.Button(frm, text="Close", command=root.destroy).pack(anchor="e", pady=12)
        root.mainloop()
        return

    session = QuizSession(questions)
    header = ttk.Label(frm, font=("TkDefaultFont", 11, "bold"))
    header.pack(anchor="w")
    clock_lbl = ttk.Label(frm, foreground="#666")
    clock_lbl.pack(anchor="w")
    text = tk.Text(frm, height=8, wrap="word", relief="flat", background=root.cget("background"))
    text.pack(fill="x", pady=(8, 8))
    body = ttk.Frame(frm)
    body.pack(fill="both", expand=True)
    nav = ttk.Frame(frm)
    nav.pack(fill="x", pady=(8, 0))

    choice_var = tk.StringVar()
    entry: tk.Text | None = None

    def save_current() -> None:
        q = session.current
        if q["type"] == "multiple_choice" and q["choices"]:
            session.answer(choice_var.get() or None)
        elif entry is not None:
            session.answer(entry.get("1.0", "end"))

    def show() -> None:
        nonlocal entry
        q = session.current
        header.config(text=f"Question {session.index + 1} of {len(questions)}")
        text.config(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", q["question"])
        text.config(state="disabled")
        for w in body.winfo_children():
            w.destroy()
        entry = None
        current = session.answers[q["number"]] or ""
        if q["type"] == "multiple_choice" and q["choices"]:
            choice_var.set(current)
            for i, opt in enumerate(q["choices"]):
                letter = chr(ord("A") + i)
                ttk.Radiobutton(body, text=f"{letter}. {opt}", value=letter, variable=choice_var,
                                command=save_current).pack(anchor="w", pady=2)
        else:
            if q["type"] == "worked_problem":
                ttk.Label(body, text=f"Write your work on paper or the tablet, on a page labeled Q{q['number']} in the top corner. "
                                     "You can add a final answer here too.", wraplength=700, foreground="#444").pack(anchor="w", pady=(0, 4))
            entry = tk.Text(body, height=7, wrap="word")
            entry.insert("1.0", current)
            entry.pack(fill="both", expand=True)
            entry.bind("<KeyRelease>", lambda _e: save_current())
            entry.focus_set()
        prev_btn.state(["!disabled"] if session.index > 0 else ["disabled"])
        next_btn.config(text="Next" if session.index < len(questions) - 1 else "Review and submit")

    def move(delta: int) -> None:
        save_current()
        if session.index + delta >= len(questions):
            submit()
            return
        session.go(session.index + delta)
        show()

    def tick() -> None:
        n = session.current["number"]
        shown = session.seconds[n] + (session.clock() - session._shown_at)
        clock_lbl.config(text=f"Time on this question: {int(shown // 60)}:{int(shown % 60):02d}")
        root.after(500, tick)

    def submit() -> None:
        save_current()
        blank = session.unanswered()
        msg = "Submit your answers? You cannot change them afterward."
        if blank:
            msg = f"Question{'s' if len(blank) > 1 else ''} {', '.join(map(str, blank))} {'are' if len(blank) > 1 else 'is'} blank. " + msg
        if not messagebox.askyesno("Submit quiz", msg, parent=root):
            return
        with db.connect() as conn:
            profile.window_submit(conn, quiz_id, session.responses())
        written_work()

    def written_work() -> None:
        for w in frm.winfo_children():
            w.destroy()
        ttk.Label(frm, text="Answers submitted.", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        has_worked = any(q["type"] == "worked_problem" for q in questions)
        ttk.Label(frm, wraplength=700, text=(
            "Add your written work now: pages labeled with the question number in the top corner. "
            "Plug in the reMarkable and pull the notebook, or pick a scan or photo." if has_worked else
            "If you wrote any work on paper or the tablet, you can add it now.")).pack(anchor="w", pady=(6, 10))
        status = ttk.Label(frm, foreground="#444")
        status.pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(frm)
        buttons.pack(anchor="w")

        def from_tablet() -> None:
            try:
                docs = tablet_notebooks(cfg)
            except Exception:  # noqa: BLE001
                docs = []
            if not docs:
                messagebox.showinfo("Oso", "The reMarkable is not connected. Plug it in with the cable, make sure "
                                           "USB web interface is on in its storage settings, and try again.", parent=root)
                return
            pick = tk.Toplevel(root)
            pick.title("Pick the notebook")
            lb = tk.Listbox(pick, width=60, height=min(12, len(docs)))
            for d in docs:
                lb.insert("end", d["_path"])
            lb.selection_set(0)
            lb.pack(padx=12, pady=12)

            def take() -> None:
                sel = lb.curselection()
                if not sel:
                    return
                pick.destroy()
                try:
                    with db.connect() as conn:
                        n = pull_from_tablet(conn, cfg, quiz, docs[sel[0]])
                    status.config(text=f"Added {n} page{'s' if n != 1 else ''} from the tablet.")
                except Exception:  # noqa: BLE001
                    messagebox.showerror("Oso", "Could not download that notebook from the tablet. Check the cable and try again.", parent=root)

            ttk.Button(pick, text="Add these pages", command=take).pack(pady=(0, 12))

        def from_file() -> None:
            paths = filedialog.askopenfilenames(parent=root, title="Pick your scans or photos",
                                                filetypes=[("Scans and photos", "*.pdf *.png *.jpg *.jpeg")])
            if not paths:
                return
            try:
                with db.connect() as conn:
                    n = import_work(conn, cfg, quiz, [Path(p) for p in paths], "file")
                status.config(text=f"Added {n} page{'s' if n != 1 else ''}.")
            except Exception:  # noqa: BLE001
                messagebox.showerror("Oso", "Could not read those files. Use PDF, PNG, or JPG.", parent=root)

        ttk.Button(buttons, text="Pull from reMarkable", command=from_tablet).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Pick a scan or photo…", command=from_file).grid(row=0, column=1, padx=(0, 8))
        ttk.Label(frm, wraplength=700, text="When you're done, close this window and tell Claude in the chat: \"I finished the quiz.\"").pack(anchor="w", pady=(18, 6))
        ttk.Button(frm, text="Done", command=root.destroy).pack(anchor="e")

    prev_btn = ttk.Button(nav, text="Previous", command=lambda: move(-1))
    prev_btn.pack(side="left")
    next_btn = ttk.Button(nav, command=lambda: move(1))
    next_btn.pack(side="right")
    show()
    tick()
    root.mainloop()


if __name__ == "__main__":
    run(int(sys.argv[1]))
