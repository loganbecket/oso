"""The Oso window (tkinter, ships with Python): a status panel first, then the settings.

The status panel shows the same facts as `oso doctor`, with a button beside anything that needs
doing; its buttons run the same actions Claude runs when asked (`actions.py`). Saving the settings
writes the config, stores any secrets in the credential store, reschedules the check if the
interval changed, and can run the health check so the result is visible right away.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config as cfgmod
from . import secrets

TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
    "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Vancouver", "Europe/London",
    "Europe/Paris", "Europe/Berlin", "Asia/Tokyo", "Asia/Shanghai", "Asia/Kolkata", "Australia/Sydney", "UTC",
]


DOT = {"ok": "#2e7d32", "warn": "#b26a00", "fail": "#c62828"}


def open_settings(cfg: cfgmod.Config) -> None:
    import os
    import threading

    from . import actions
    from .doctor import ACTIONS

    root = tk.Tk()
    from . import version_label

    root.title(version_label(cfg.installed_version))
    root.geometry("1000x760")
    pad = {"padx": 8, "pady": 4}
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)
    status_tab = ttk.Frame(notebook, padding=12)
    settings_outer = ttk.Frame(notebook)
    notebook.add(status_tab, text="Status")
    grades_tab = ttk.Frame(notebook, padding=12)
    notebook.add(grades_tab, text="Grades")
    quizzes_tab = ttk.Frame(notebook, padding=12)
    notebook.add(quizzes_tab, text="Quizzes")
    notebook.add(settings_outer, text="Settings")

    # One window at a time: record ours, and come to the front when Claude asks for the window again.
    actions.window_pid_path().write_text(str(os.getpid()), encoding="utf-8")
    raise_file = actions.raise_request_path()
    raise_file.unlink(missing_ok=True)

    def watch_for_raise() -> None:
        if raise_file.exists():
            raise_file.unlink(missing_ok=True)
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            root.after(300, lambda: root.attributes("-topmost", False))
            root.focus_force()
        root.after(1000, watch_for_raise)

    # ---- Status and Actions ----------------------------------------------------------------------------
    actions_tab = ttk.Frame(notebook, padding=12)
    notebook.insert(settings_outer, actions_tab, text="Actions")
    results = []
    from tkinter import font as tkfont

    bold = tkfont.nametofont("TkDefaultFont").copy()
    bold.configure(weight="bold")

    def result_box(parent, above) -> None:
        """Where a button's reply appears: plain text under a line, shown once there is something to say."""
        box = ttk.Frame(parent)
        ttk.Separator(box).pack(fill="x", pady=(0, 8))
        text = ttk.Label(box, wraplength=920, justify="left", font=bold)
        text.pack(anchor="w")
        results.append((box, text, above))

    def show(message: str) -> None:
        for box, text, above in results:
            text.configure(text=message)
            if not box.winfo_ismapped():
                box.pack(side="bottom", fill="x", pady=(10, 0), before=above)

    busy = {"on": False}

    def run(label: str, fn) -> None:
        """Run an action without freezing the window, then show its sentence and refresh the status."""
        if busy["on"]:
            show("Still working on the last request…")
            return
        busy["on"] = True
        show(f"{label}…")
        box: dict = {}
        threading.Thread(target=lambda: box.update(text=_safe(fn)), daemon=True).start()

        def wait() -> None:
            if "text" in box:
                busy["on"] = False
                show(box["text"])
                refresh()
            else:
                root.after(300, wait)

        root.after(300, wait)

    def connect_calendar() -> None:
        from pathlib import Path

        path = filedialog.askopenfilename(title="Choose the OAuth client file from Google Cloud", filetypes=[("JSON", "*.json"), ("All files", "*")])
        if not path:
            show("No file chosen.")
            return
        run("Connecting Google Calendar (sign in in your browser)", lambda: _connect_calendar(cfg, Path(path)))

    fixes = {
        "update": ("Updating Oso", actions.update_oso),
        "fix": ("Fixing", lambda: actions.health_check(fix=True)),
        "sync": ("Starting a check", actions.sync_now),
        "connect_canvas": ("Opening the Canvas sign-in", actions.connect_canvas),
        "backup": ("Backing up", actions.backup_now),
    }

    def connect_email() -> None:
        client = _email_client_file()  # a dialog, so on this thread; the sign-in itself runs in the background
        if client is False:
            show("No file chosen.")
            return
        run("Opening the Google sign-in", lambda: actions.connect_email(client))

    def connect_tasks() -> None:
        client = _email_client_file()  # the same Google client as email; asked for only if Oso doesn't have it
        if client is False:
            show("No file chosen.")
            return
        run("Opening the Google sign-in", lambda: actions.connect_tasks(client))

    top = ttk.Frame(status_tab)
    top.pack(fill="x")
    result_box(status_tab, top)
    ttk.Label(top, text="How Oso is doing", font=("TkDefaultFont", 12, "bold")).pack(side="left")
    refresh_button = ttk.Button(top, text="Refresh", command=lambda: (show("Up to date."), refresh()))
    refresh_button.pack(side="right", padx=(0, 16))
    lines_frame = _scrolling(status_tab, padding=(0, 8, 0, 0))
    _line_up(refresh_button, lines_frame)
    lines_frame.columnconfigure(1, weight=1)

    def refresh() -> None:
        """Gather the status off the window's thread (it asks GitHub and the credential store), then draw it."""
        for w in lines_frame.winfo_children():
            w.destroy()
        ttk.Label(lines_frame, text="Checking…", foreground="#666").grid(row=0, column=0, sticky="w", padx=16, pady=3)
        box: dict = {}

        def gather() -> None:
            try:
                box["checks"] = actions.status()
            except Exception as e:  # noqa: BLE001
                from .sync import plain_error

                box["checks"] = [{"status": "fail", "text": f"Oso couldn't check itself: {plain_error(e)}", "action": None}]

        threading.Thread(target=gather, daemon=True).start()

        def wait() -> None:
            if "checks" in box:
                draw(box["checks"])
            else:
                root.after(200, wait)

        root.after(200, wait)

    def draw(checks: list[dict]) -> None:
        for w in lines_frame.winfo_children():
            w.destroy()
        order = {"fail": 0, "warn": 1, "ok": 2}
        for i, c in enumerate(sorted(checks, key=lambda c: order.get(c["status"], 3))):
            # The light and the text share a frame, so the light sits on the text's first line even when a button
            # makes the row taller.
            line = ttk.Frame(lines_frame)
            line.grid(row=i, column=1, sticky="w", pady=1)
            ttk.Label(line, text="●", foreground=DOT.get(c["status"], "#666")).pack(side="left", anchor="n", padx=(0, 6))
            ttk.Label(line, text=c["text"], wraplength=660, justify="left").pack(side="left", anchor="n")
            action = c.get("action")
            if action == "connect_email":
                ttk.Button(lines_frame, text=ACTIONS[action], command=connect_email).grid(row=i, column=2, sticky="ew", padx=(16, 16), pady=3)
            elif action == "connect_tasks":
                ttk.Button(lines_frame, text=ACTIONS[action], command=connect_tasks).grid(row=i, column=2, sticky="ew", padx=(16, 16), pady=3)
            elif action == "connect_calendar":
                ttk.Button(lines_frame, text=ACTIONS[action], command=connect_calendar).grid(row=i, column=2, sticky="ew", padx=(16, 16), pady=3)
            elif action in fixes:
                label, fn = fixes[action]
                ttk.Button(lines_frame, text=ACTIONS[action], command=lambda label=label, fn=fn: run(label, fn)).grid(
                    row=i, column=2, sticky="ew", padx=(16, 16), pady=3)

    groups = [
        ("Keep Oso running", [
            ("Health check and fix", lambda: run("Checking and fixing", lambda: actions.health_check(fix=True))),
            ("Sync now", lambda: run("Starting a check", actions.sync_now)),
            ("Update Oso", lambda: run("Updating Oso", actions.update_oso)),
            ("Back up now", lambda: run("Backing up", actions.backup_now)),
            ("Transcribe now", lambda: run("Starting transcription", actions.transcribe_now)),
        ]),
        ("Connections", [
            ("Sign in to Canvas", lambda: run("Opening the Canvas sign-in", actions.connect_canvas)),
            ("Canvas username and password…", lambda: show(_canvas_login(root))),
            ("Disconnect Canvas", lambda: run("Disconnecting Canvas", actions.disconnect_canvas)),
            ("Connect Google Calendar…", connect_calendar),
            ("Connect email…", connect_email),
            ("Disconnect email", lambda: run("Disconnecting email", actions.disconnect_email)),
            ("Connect Google Tasks…", connect_tasks),
            ("Disconnect Google Tasks", lambda: run("Disconnecting Google Tasks", actions.disconnect_tasks)),
            ("Connect GroupMe…", lambda: show(_connect_groupme(root))),
            ("Disconnect GroupMe", lambda: run("Disconnecting GroupMe", actions.disconnect_groupme)),
        ]),
        ("Books and websites", [
            ("Books", lambda: run("Looking at books", actions.books)),
            ("Read a book again…", lambda: show(_reread_book(root))),
            ("Websites", lambda: run("Looking at websites", actions.websites)),
            ("Check websites now", lambda: run("Checking websites", lambda: actions.websites(check=True))),
            ("Add a website…", lambda: show(_add_website(root, cfg))),
        ]),
    ]
    ttk.Label(actions_tab, text="Starting over (fresh start) is only in a command window, on purpose: run 'oso fresh-start' (PowerShell on Windows, Terminal on a Mac).",
              foreground="#666").pack(side="bottom", anchor="w", pady=(6, 0))
    acts = ttk.Frame(actions_tab)
    acts.pack(anchor="nw", fill="x")
    result_box(actions_tab, acts)
    for col, (title, items) in enumerate(groups):
        acts.columnconfigure(col, weight=1, uniform="groups")
        group = ttk.LabelFrame(acts, text=title, padding=10)
        group.grid(row=0, column=col, sticky="nsew", padx=6)
        for text, cmd in items:
            ttk.Button(group, text=text, command=cmd).pack(fill="x", pady=3)
    refresh()

    # ---- Grades: each class's grade from Canvas, lowest first, with the work pulling it down ------------
    gtop = ttk.Frame(grades_tab)
    gtop.pack(fill="x")
    ttk.Label(gtop, text="Your grades", font=("TkDefaultFont", 12, "bold")).pack(side="left")
    grades_asof = ttk.Label(grades_tab, foreground="#666")
    grades_asof.pack(side="bottom", anchor="w", pady=(6, 0))
    grade_rows = _scrolling(grades_tab, padding=(0, 8, 0, 0))
    grade_rows.columnconfigure(0, weight=1)

    def list_grades() -> None:
        from datetime import datetime as _dt

        for w in grade_rows.winfo_children():
            w.destroy()
        grades_asof.configure(text="")
        try:
            rows = actions.grades()
        except Exception as e:  # noqa: BLE001
            from .sync import plain_error

            ttk.Label(grade_rows, text=f"Oso couldn't list your grades ({plain_error(e)}).").grid(row=0, column=0, sticky="w")
            return
        if not rows:
            ttk.Label(grade_rows, text="No grades yet. They appear here once Oso is signed in to Canvas and an instructor posts one.",
                      foreground="#666").grid(row=0, column=0, columnspan=3, sticky="w")
            return
        # Grid lines: the cells sit 1px apart on a gray frame, so the gray shows through as the lines.
        table = tk.Frame(grade_rows, bg="#b0b0b0")
        table.grid(row=0, column=0, columnspan=3, sticky="ew", padx=(0, 16))
        table.columnconfigure(2, weight=1)
        cell_bg = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        cells = [(("Course", "Grade", "Note"), bold)] + [((r["course"], r["grade"], r["note"]), None) for r in rows]
        for i, (texts, font) in enumerate(cells):
            for col, (text, wrap) in enumerate(zip(texts, (260, 0, 440))):
                tk.Label(table, text=text, font=font or "TkDefaultFont", bg=cell_bg, wraplength=wrap, justify="left",
                         anchor="nw", padx=8, pady=4).grid(row=i, column=col, sticky="nsew",
                                                           padx=(1, 1 if col == 2 else 0), pady=(1, 1 if i == len(cells) - 1 else 0))
        read = max(r["read_at"] for r in rows)
        grades_asof.configure(text=f"From Canvas as of {_dt.fromisoformat(read).astimezone(cfg.tz).strftime('%a %b %d, %I:%M %p').replace(' 0', ' ')}. "
                                   "An estimate is the share of points earned so far, for classes where the instructor hides the grade.")

    grades_refresh = ttk.Button(gtop, text="Refresh", command=list_grades)
    grades_refresh.pack(side="right", padx=(0, 16))
    _line_up(grades_refresh, grade_rows)
    list_grades()

    # ---- Quizzes: every quiz, opened in the quiz window (read-only once taken) ------------------------
    qtop = ttk.Frame(quizzes_tab)
    qtop.pack(fill="x")
    ttk.Label(qtop, text="Your quizzes", font=("TkDefaultFont", 12, "bold")).pack(side="left")
    names = ["All courses"] + [c.name for c in cfg.courses]
    course_var = tk.StringVar(value="All courses")
    result_box(quizzes_tab, qtop)
    quiz_rows = _scrolling(quizzes_tab, padding=(0, 8, 0, 0))
    quiz_rows.columnconfigure(1, weight=1)

    def list_quizzes() -> None:
        from datetime import datetime as _dt

        for w in quiz_rows.winfo_children():
            w.destroy()
        want = next((c.code for c in cfg.courses if c.name == course_var.get()), None)
        try:
            rows = [q for q in actions.quizzes() if want is None or q["course"].lower() == want.lower()]
        except Exception as e:  # noqa: BLE001
            from .sync import plain_error

            ttk.Label(quiz_rows, text=f"Oso couldn't list the quizzes ({plain_error(e)}).").grid(row=0, column=0, sticky="w")
            return
        retakes = {q["retake_of"]: q for q in rows if q.get("kind") == "retake"}
        rows = [q for q in rows if q.get("kind") != "retake"]  # a retake shows on its quiz's row
        if not rows:
            ttk.Label(quiz_rows, text="No quizzes yet. Ask Claude to quiz you.", foreground="#666").grid(row=0, column=0, sticky="w")

        def score_of(q: dict) -> str:
            return f"{q['score']:g}%" if q["score"] is not None else {"handed_out": "not taken yet"}.get(q["status"], "not graded yet")

        for i, q in enumerate(rows):
            c = cfg.course_for(q["course"])
            day = _dt.fromisoformat(q["handed_out_at"]).astimezone(cfg.tz).strftime("%a %b %d")
            again = retakes.get(q["quiz_id"])
            what = f"{c.name if c else q['course']}: {', '.join(q['topics'][:4])} ({q['questions']} questions)"
            if q.get("kind") == "new_version":
                what = "New version. " + what
            ttk.Label(quiz_rows, text=day, width=11).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(quiz_rows, text=what, wraplength=420, justify="left").grid(row=i, column=1, sticky="w", pady=2)
            ttk.Label(quiz_rows, text=score_of(q) + (f", retake {score_of(again)}" if again else ""), width=24).grid(
                row=i, column=2, sticky="w", pady=2)
            buttons = ttk.Frame(quiz_rows)
            buttons.grid(row=i, column=3, sticky="e", padx=(8, 16), pady=2)
            taken = q["status"] != "handed_out"
            ttk.Button(buttons, text="Review" if taken else "Take",
                       command=lambda n=q["quiz_id"]: show(actions.open_quiz(n))).pack(side="left", padx=2)
            if taken and again:
                ttk.Button(buttons, text="Review retake" if again["status"] != "handed_out" else "Take retake",
                           command=lambda n=again["quiz_id"]: show(actions.open_quiz(n))).pack(side="left", padx=2)
            elif taken:
                ttk.Button(buttons, text="Retake", command=lambda n=q["quiz_id"]: (show(actions.retake_quiz(n)), list_quizzes())).pack(side="left", padx=2)
            if taken:
                ttk.Button(buttons, text="New version", command=lambda n=q["quiz_id"]: show(actions.new_version(n))).pack(side="left", padx=2)
            ttk.Button(buttons, text="Delete", command=lambda q=q, day=day, c=c: delete_quiz(q, day, c)).pack(side="left", padx=2)

    def delete_quiz(q: dict, day: str, c) -> None:
        sure = messagebox.askyesno(
            "Delete this quiz?",
            f"Delete the {c.name if c else q['course']} quiz from {day} ({', '.join(q['topics'][:4])})?\n\n"
            "Its questions, answers, and grades (and its retake, if any) are removed for good, and it no longer counts toward where you stand "
            "in any topic. This can't be undone.",
            icon="warning", default="no", parent=root)
        if sure:
            show(actions.delete_quiz(q["quiz_id"]))
            list_quizzes()

    quiz_refresh = ttk.Button(qtop, text="Refresh", command=list_quizzes)
    quiz_refresh.pack(side="right", padx=(0, 16))
    _line_up(quiz_refresh, quiz_rows)
    picker = ttk.Combobox(qtop, textvariable=course_var, values=names, state="readonly", width=28)
    picker.pack(side="right", padx=(0, 12))
    picker.bind("<<ComboboxSelected>>", lambda _e: list_quizzes())
    list_quizzes()

    # ---- Settings (scrolls: there are many) -----------------------------------------------------------
    frm = _scrolling(settings_outer, padding=12)

    row = 0

    def label(text: str, hint: str | None = None):
        nonlocal row
        ttk.Label(frm, text=text).grid(row=row, column=0, sticky="w", **pad)
        if hint:
            ttk.Label(frm, text=hint, foreground="#666", wraplength=280, justify="left").grid(row=row, column=2, sticky="w", **pad)

    # Vault
    label("Vault folder", "Your Obsidian vault, inside your Google Drive folder")
    vault_var = tk.StringVar(value=str(cfg.vault))
    ttk.Entry(frm, textvariable=vault_var, width=36).grid(row=row, column=1, sticky="we", **pad)
    row += 1
    ttk.Button(frm, text="Choose…", command=lambda: vault_var.set(filedialog.askdirectory() or vault_var.get())).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Timezone
    label("Time zone")
    tz_var = tk.StringVar(value=cfg.timezone)
    ttk.Combobox(frm, textvariable=tz_var, values=TIMEZONES, width=30).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Interval
    label("Check for changes every", "minutes; 15 is a good default")
    interval_var = tk.IntVar(value=cfg.sync_interval_minutes)
    ttk.Spinbox(frm, from_=5, to=720, increment=5, textvariable=interval_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Urgent window
    label("Treat a moved or new item as urgent when due within", "days")
    urgent_var = tk.IntVar(value=cfg.urgent_days)
    ttk.Spinbox(frm, from_=1, to=60, textvariable=urgent_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Stale hours
    label("Warn when a source has not synced for", "hours")
    stale_var = tk.IntVar(value=cfg.stale_hours)
    ttk.Spinbox(frm, from_=1, to=168, textvariable=stale_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Quiet hours
    label("Quiet hours", "for example 22:00-07:00; leave empty for none")
    quiet_var = tk.StringVar(value=cfg.quiet_hours or "")
    ttk.Entry(frm, textvariable=quiet_var, width=16).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Transcription and models
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    label("Picture size for reading handwriting", "pixels tall; bigger reads small writing better but uses more of your Claude plan; 1200 is a good middle")
    height_var = tk.IntVar(value=cfg.render_height_px)
    ttk.Spinbox(frm, from_=600, to=2400, increment=100, textvariable=height_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Model for reading handwriting", "sonnet is accurate and light on usage")
    tmodel_var = tk.StringVar(value=cfg.transcribe_model)
    ttk.Combobox(frm, textvariable=tmodel_var, values=["sonnet", "opus", "haiku"], width=12).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Model for study guides and practice tests", "opus by default; type another name your plan offers")
    emodel_var = tk.StringVar(value=cfg.exam_model)
    ttk.Combobox(frm, textvariable=emodel_var, values=["opus", "sonnet"], width=12).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Model for rules and reading messages", "acts on your rules and reads school email and GroupMe in the background; sonnet by default")
    bmodel_var = tk.StringVar(value=cfg.background_model)
    ttk.Combobox(frm, textvariable=bmodel_var, values=["sonnet", "opus", "haiku"], width=12).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    label("Cap on how much of a note is read per call", "characters; 0 turns the cap off")
    cap_var = tk.IntVar(value=cfg.read_cap_chars)
    ttk.Spinbox(frm, from_=0, to=200000, increment=2000, textvariable=cap_var, width=8).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    instr_var = tk.BooleanVar(value=cfg.write_vault_instructions)
    ttk.Checkbutton(frm, text="Keep a CLAUDE.md in the vault so Claude Code knows the layout", variable=instr_var).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    row += 1

    label("Updates", "stable: tagged versions only; latest: every change as it lands")
    channel_var = tk.StringVar(value=cfg.channel)
    ttk.Combobox(frm, textvariable=channel_var, values=["stable", "latest"], width=12, state="readonly").grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Learner profile
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    label("A topic is strong at", "percent or better, from quiz and check results")
    strong_var = tk.IntVar(value=cfg.strong_percent)
    ttk.Spinbox(frm, from_=50, to=100, increment=5, textvariable=strong_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("...over at least", "results in the last 60 days")
    strong_n_var = tk.IntVar(value=cfg.strong_min_results)
    ttk.Spinbox(frm, from_=1, to=50, textvariable=strong_n_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("A topic counts as untested with fewer than", "results")
    untested_var = tk.IntVar(value=cfg.untested_below)
    ttk.Spinbox(frm, from_=1, to=20, textvariable=untested_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("A result this old counts half as much", "days")
    half_var = tk.IntVar(value=cfg.half_life_days)
    ttk.Spinbox(frm, from_=3, to=180, textvariable=half_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Check readiness for exams within", "days")
    ready_var = tk.IntVar(value=cfg.readiness_days)
    ttk.Spinbox(frm, from_=1, to=30, textvariable=ready_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Warn when the last quiz on an exam's topics is below", "percent")
    warn_var = tk.IntVar(value=cfg.quiz_warning_percent)
    ttk.Spinbox(frm, from_=0, to=100, increment=5, textvariable=warn_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    auto_read_var = tk.BooleanVar(value=cfg.auto_read)
    ttk.Checkbutton(frm, text="Have Claude read handwriting, equations, tables, and drawings automatically", variable=auto_read_var).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    row += 1
    label("Daily limit on pages Claude reads automatically", "0 means no limit; set one if it uses too much of your Claude plan")
    read_limit_var = tk.IntVar(value=cfg.auto_read_per_day)
    ttk.Spinbox(frm, from_=0, to=1000, increment=10, textvariable=read_limit_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    label("Backup folder", "optional: a NAS share or drive; Oso copies your vault and records there nightly")
    backup_var = tk.StringVar(value=cfg.backup_folder or "")
    ttk.Entry(frm, textvariable=backup_var, width=36).grid(row=row, column=1, sticky="we", **pad)
    row += 1
    canvas_notify_var = tk.BooleanVar(value=cfg.canvas_notify)
    ttk.Checkbutton(frm, text="Show a notification when Canvas needs me to sign in again", variable=canvas_notify_var).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    row += 1

    # reMarkable folder
    label("Tablet folder holding the course folders", "leave empty if course folders are at the tablet's top level")
    rm_var = tk.StringVar(value=cfg.remarkable_folder or "")
    ttk.Entry(frm, textvariable=rm_var, width=24).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    # Courses: mute checkboxes
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    ttk.Label(frm, text="Courses (tick to mute alerts for a course)").grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    row += 1
    mute_vars: dict[str, tk.BooleanVar] = {}
    muted = {m.lower() for m in cfg.muted_courses}
    for c in cfg.courses:
        v = tk.BooleanVar(value=c.code.lower() in muted)
        mute_vars[c.code] = v
        ttk.Checkbutton(frm, text=f"{c.name}  ({c.code}, folder Courses/{c.folder})", variable=v).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1
    if not cfg.courses:
        ttk.Label(frm, text="No courses yet. Ask Claude to set one up from a syllabus.", foreground="#666").grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

    # School email and GroupMe
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    label("Email senders to ignore", "addresses, @domains, or mailing lists, separated by commas")
    senders_var = tk.StringVar(value=", ".join(cfg.muted_senders))
    ttk.Entry(frm, textvariable=senders_var, width=36).grid(row=row, column=1, sticky="we", **pad)
    row += 1
    label("Daily limit on messages Claude reads", "0 means no limit; set one if it uses too much of your Claude plan")
    msg_limit_var = tk.IntVar(value=cfg.message_reads_per_day)
    ttk.Spinbox(frm, from_=0, to=2000, increment=25, textvariable=msg_limit_var, width=6).grid(row=row, column=1, sticky="w", **pad)
    row += 1
    from . import db as dbmod
    from . import groupme

    try:
        with dbmod.connect() as conn:
            known_groups = groupme.groups(conn)
    except Exception:  # noqa: BLE001
        known_groups = []
    group_vars: dict[str, tk.BooleanVar] = {}
    if known_groups:
        ttk.Label(frm, text="GroupMe groups (tick to stop reading a group)").grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1
        muted_groups = set(cfg.muted_groups)
        for g in known_groups:
            v = tk.BooleanVar(value=g["id"] in muted_groups or g["name"] in muted_groups)
            group_vars[g["id"]] = v
            ttk.Checkbutton(frm, text=g["name"], variable=v).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
            row += 1

    # Canvas
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    feed_state = "stored" if secrets.get(secrets.CANVAS_FEED_URL) else "not set"
    label("Canvas calendar feed URL", f"currently {feed_state}; paste a new one to replace it")
    feed_var = tk.StringVar()
    ttk.Entry(frm, textvariable=feed_var, width=36, show="•").grid(row=row, column=1, sticky="we", **pad)
    row += 1
    label("Canvas address", "only if your school allows access tokens")
    base_var = tk.StringVar(value=secrets.get(secrets.CANVAS_BASE_URL) or "")
    ttk.Entry(frm, textvariable=base_var, width=36).grid(row=row, column=1, sticky="we", **pad)
    row += 1
    tok_state = "stored" if secrets.get(secrets.CANVAS_TOKEN) else "not set"
    label("Canvas access token", f"currently {tok_state}; paste a new one to replace it")
    tok_var = tk.StringVar()
    ttk.Entry(frm, textvariable=tok_var, width=36, show="•").grid(row=row, column=1, sticky="we", **pad)
    row += 1

    # Buttons and result
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    def save(and_apply: bool) -> None:
        from pathlib import Path

        try:
            old_interval = cfg.sync_interval_minutes
            cfg.vault = Path(vault_var.get()).expanduser()
            cfg.timezone = tz_var.get().strip() or cfg.timezone
            cfg.sync_interval_minutes = max(5, int(interval_var.get()))
            cfg.urgent_days = max(1, int(urgent_var.get()))
            cfg.stale_hours = max(1, int(stale_var.get()))
            cfg.quiet_hours = quiet_var.get().strip() or None
            cfg.remarkable_folder = rm_var.get().strip() or None
            cfg.render_height_px = max(600, int(height_var.get()))
            cfg.transcribe_model = tmodel_var.get().strip() or "sonnet"
            cfg.exam_model = emodel_var.get().strip() or "opus"
            cfg.background_model = bmodel_var.get().strip() or "sonnet"
            cfg.read_cap_chars = max(0, int(cap_var.get()))
            cfg.write_vault_instructions = bool(instr_var.get())
            cfg.channel = channel_var.get() or "stable"
            cfg.strong_percent = min(100, max(50, int(strong_var.get())))
            cfg.strong_min_results = max(1, int(strong_n_var.get()))
            cfg.untested_below = max(1, int(untested_var.get()))
            cfg.half_life_days = max(3, int(half_var.get()))
            cfg.readiness_days = max(1, int(ready_var.get()))
            cfg.quiz_warning_percent = min(100, max(0, int(warn_var.get())))
            cfg.canvas_notify = bool(canvas_notify_var.get())
            cfg.auto_read = bool(auto_read_var.get())
            cfg.auto_read_per_day = max(0, int(read_limit_var.get()))
            new_backup = backup_var.get().strip() or None
            if new_backup and new_backup != cfg.backup_folder:
                from . import backup

                backup.check_folder(Path(new_backup))  # a plain sentence if it can't be written to
            cfg.backup_folder = new_backup
            cfg.muted_courses = [code for code, v in mute_vars.items() if v.get()]
            cfg.muted_senders = [s.strip().lower() for s in senders_var.get().split(",") if s.strip()]
            cfg.message_reads_per_day = max(0, int(msg_limit_var.get()))
            known_ids = set(group_vars)
            cfg.muted_groups = [g for g in cfg.muted_groups if g not in known_ids] + [gid for gid, v in group_vars.items() if v.get()]
            cfgmod.save(cfg)
            if feed_var.get().strip():
                secrets.set(secrets.CANVAS_FEED_URL, feed_var.get().strip())
                feed_var.set("")
            if base_var.get().strip():
                secrets.set(secrets.CANVAS_BASE_URL, base_var.get().strip())
            if tok_var.get().strip():
                secrets.set(secrets.CANVAS_TOKEN, tok_var.get().strip())
                tok_var.set("")
        except (ValueError, tk.TclError):
            messagebox.showerror("Oso", "One of the number fields is blank or not a number. Fix it and save again.")
            return
        except Exception as e:  # noqa: BLE001
            from .sync import plain_error

            messagebox.showerror("Oso", f"Could not save: {plain_error(e)}")
            return
        lines = ["Saved."]
        if and_apply:
            def apply_and_check() -> str:
                from . import doctor

                out = list(lines)
                if cfg.sync_interval_minutes != old_interval:
                    out.append(_reschedule(cfg.sync_interval_minutes))
                out += ["", doctor.format_report(doctor.run(fix=True))]
                return "\n".join(out)

            run("Saving and checking", apply_and_check)
            return
        show_saved("\n".join(lines))

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    ttk.Button(btns, text="Save", command=lambda: save(False)).grid(row=0, column=0, padx=4)
    ttk.Button(btns, text="Save and check", command=lambda: save(True)).grid(row=0, column=1, padx=4)
    row += 1
    settings_result = ttk.Label(frm, wraplength=900, justify="left", font=bold)
    settings_result.grid(row=row, column=0, columnspan=3, sticky="w", **pad)

    def show_saved(text: str) -> None:
        settings_result.configure(text=text)
        refresh()


    def close() -> None:
        actions.window_pid_path().unlink(missing_ok=True)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(1000, watch_for_raise)
    root.mainloop()


def _line_up(button, scrolling: ttk.Frame) -> None:
    """Keep a button above a scrolling list lined up with the list's buttons, which sit left of the scroll bar."""
    scrolling.scrollbar.bind("<Configure>", lambda e: button.pack_configure(padx=(0, 16 + e.width)), add="+")


def _scrolling(parent, padding=0) -> ttk.Frame:
    """A frame inside parent that scrolls when its contents are taller than the window."""
    outer = ttk.Frame(parent)
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, highlightthickness=0)
    bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas, padding=padding)
    inner.scrollbar = bar
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    def wheel(e) -> None:
        # Scroll only the area under the pointer, and only when there is something to scroll.
        w = canvas.winfo_containing(e.x_root, e.y_root)
        while w is not None and w is not canvas:
            w = w.master
        if w is canvas and canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(-1 if (getattr(e, "num", 0) == 4 or e.delta > 0) else 1, "units")

    for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind_all(event, wheel, add="+")
    return inner


def _safe(fn) -> str:
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        from .sync import plain_error

        return f"That didn't work: {plain_error(e)}"


def _reread_book(root) -> str:
    from tkinter import simpledialog

    from . import actions

    title = simpledialog.askstring("Read a book again", "Which book? (its title or folder name)", parent=root)
    return actions.reread_book(title) if title else "Nothing changed."


def _add_website(root, cfg) -> str:
    from tkinter import simpledialog

    from . import actions

    if not cfg.courses:
        return "Set up a course first."
    names = ", ".join(f"{c.name} ({c.code})" for c in cfg.courses)
    course = simpledialog.askstring("Follow a website", f"Which course? ({names})", parent=root)
    if not course:
        return "Nothing changed."
    match = next((c for c in cfg.courses if course.strip().lower() in (c.code.lower(), c.name.lower())), None)
    if match is None:
        return f"No course called {course!r}."
    url = simpledialog.askstring("Follow a website", "The page's address:", parent=root)
    return actions.add_website(match.code, url) if url else "Nothing changed."


def _email_client_file():
    """The Google client file, asked for only if Oso doesn't have it from the calendar. None when not needed;
    False when he closed the dialog."""
    from pathlib import Path

    from . import gcal

    if gcal.client_config():
        return None
    path = filedialog.askopenfilename(title="Choose the OAuth client file from Google Cloud (the one used for the Oso calendar)",
                                      filetypes=[("JSON", "*.json"), ("All files", "*")])
    return Path(path) if path else False


def _canvas_login(root) -> str:
    from tkinter import simpledialog

    from . import actions

    user = simpledialog.askstring("Canvas sign-in", "Your school username (the one you sign in to Canvas with):", parent=root)
    if not user:
        return "Nothing changed."
    password = simpledialog.askstring("Canvas sign-in", "Your school password (paste it once; it's kept in your computer's credential store):",
                                      parent=root, show="•")
    return actions.set_canvas_login(user, password or "")


def _connect_groupme(root) -> str:
    from tkinter import simpledialog

    from . import actions

    token = simpledialog.askstring(
        "Connect GroupMe", "Sign in at dev.groupme.com, click Access Token at the top right, copy it, and paste it here:",
        parent=root, show="•")
    return actions.connect_groupme(token) if token else "Nothing changed."


def _reschedule(minutes: int) -> str:
    if sys.platform == "win32":
        from .install_windows import install_task

        return install_task(every_minutes=minutes)
    if sys.platform == "darwin":
        from .install_macos import install_agent

        return install_agent(every_minutes=minutes)
    from .install_linux import install_timer

    return install_timer(every_minutes=minutes)


def _connect_calendar(cfg, path) -> str:
    from . import gcal

    try:
        gcal.connect(path, cfg)
    except Exception as e:  # noqa: BLE001
        from .sync import plain_error

        return f"Could not connect Google Calendar: {plain_error(e)}"
    return "Connected. Oso created a calendar named 'Oso' and will put urgent changes on it."
