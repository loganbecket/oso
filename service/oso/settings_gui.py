"""A small settings window (tkinter, ships with Python) so nothing has to be edited by hand.

Saving writes the config, stores any secrets in the credential store, reschedules the watcher
if the interval changed, and runs the doctor so the result is visible right away.
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


def open_settings(cfg: cfgmod.Config) -> None:
    root = tk.Tk()
    root.title("Oso settings")
    root.resizable(False, False)
    pad = {"padx": 8, "pady": 4}
    frm = ttk.Frame(root, padding=12)
    frm.grid(sticky="nsew")

    row = 0

    def label(text: str, hint: str | None = None):
        nonlocal row
        ttk.Label(frm, text=text).grid(row=row, column=0, sticky="w", **pad)
        if hint:
            ttk.Label(frm, text=hint, foreground="#666").grid(row=row, column=2, sticky="w", **pad)

    # Vault
    label("Vault folder", "Your Obsidian vault, inside your Google Drive folder")
    vault_var = tk.StringVar(value=str(cfg.vault))
    ttk.Entry(frm, textvariable=vault_var, width=48).grid(row=row, column=1, sticky="we", **pad)
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
    label("Page image height for transcription", "pixels; 1200 reads well and keeps usage down")
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

    # Canvas
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    feed_state = "stored" if secrets.get(secrets.CANVAS_FEED_URL) else "not set"
    label("Canvas calendar feed URL", f"currently {feed_state}; paste a new one to replace it")
    feed_var = tk.StringVar()
    ttk.Entry(frm, textvariable=feed_var, width=48, show="•").grid(row=row, column=1, sticky="we", **pad)
    row += 1
    label("Canvas address", "only if your school allows access tokens")
    base_var = tk.StringVar(value=secrets.get(secrets.CANVAS_BASE_URL) or "")
    ttk.Entry(frm, textvariable=base_var, width=48).grid(row=row, column=1, sticky="we", **pad)
    row += 1
    tok_state = "stored" if secrets.get(secrets.CANVAS_TOKEN) else "not set"
    label("Canvas access token", f"currently {tok_state}; paste a new one to replace it")
    tok_var = tk.StringVar()
    ttk.Entry(frm, textvariable=tok_var, width=48, show="•").grid(row=row, column=1, sticky="we", **pad)
    row += 1

    # Buttons and result
    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    row += 1
    result = tk.Text(frm, height=8, width=90, state="disabled", wrap="word")
    result.grid(row=row + 1, column=0, columnspan=3, sticky="we", **pad)

    def show(text: str) -> None:
        result.configure(state="normal")
        result.delete("1.0", "end")
        result.insert("1.0", text)
        result.configure(state="disabled")

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
            cfg.muted_courses = [code for code, v in mute_vars.items() if v.get()]
            cfgmod.save(cfg)
            if feed_var.get().strip():
                secrets.set(secrets.CANVAS_FEED_URL, feed_var.get().strip())
                feed_var.set("")
            if base_var.get().strip():
                secrets.set(secrets.CANVAS_BASE_URL, base_var.get().strip())
            if tok_var.get().strip():
                secrets.set(secrets.CANVAS_TOKEN, tok_var.get().strip())
                tok_var.set("")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Oso", f"Could not save: {e}")
            return
        lines = ["Saved."]
        if and_apply:
            if cfg.sync_interval_minutes != old_interval:
                lines.append(_reschedule(cfg.sync_interval_minutes))
            from . import doctor

            lines.append("")
            lines.append(doctor.format_report(doctor.run(fix=True)))
        show("\n".join(lines))

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=3, sticky="w", **pad)
    ttk.Button(btns, text="Save", command=lambda: save(False)).grid(row=0, column=0, padx=4)
    ttk.Button(btns, text="Save and check", command=lambda: save(True)).grid(row=0, column=1, padx=4)
    ttk.Button(btns, text="Sync now", command=lambda: show(_sync_now())).grid(row=0, column=2, padx=4)
    ttk.Button(btns, text="Transcribe now", command=lambda: show(_transcribe_now())).grid(row=0, column=3, padx=4)
    ttk.Button(btns, text="Update Oso", command=lambda: show(_update_now())).grid(row=1, column=0, padx=4, pady=4)
    ttk.Button(btns, text="Connect Google Calendar…", command=lambda: show(_connect_calendar(cfg))).grid(row=0, column=4, padx=4)
    ttk.Button(btns, text="Connect Canvas…", command=lambda: show(_connect_canvas())).grid(row=1, column=1, padx=4, pady=4)
    ttk.Button(btns, text="Books", command=lambda: show(_books(cfg))).grid(row=1, column=3, padx=4, pady=4)
    ttk.Button(btns, text="Read a book again…", command=lambda: show(_reread_book(cfg, root))).grid(row=1, column=4, padx=4, pady=4)
    ttk.Button(btns, text="Disconnect Canvas", command=lambda: show(_disconnect_canvas())).grid(row=1, column=2, padx=4, pady=4)
    ttk.Button(btns, text="Close", command=root.destroy).grid(row=0, column=5, padx=4)

    root.mainloop()


def _reschedule(minutes: int) -> str:
    if sys.platform == "win32":
        from .install_windows import install_task

        return install_task(every_minutes=minutes)
    if sys.platform == "darwin":
        from .install_macos import install_agent

        return install_agent(every_minutes=minutes)
    from .install_linux import install_timer

    return install_timer(every_minutes=minutes)


def _update_now() -> str:
    from . import config as cfgmod
    from . import update

    return update.run(cfgmod.load())


def _books(cfg) -> str:
    from . import books

    rows = books.progress(cfg)
    if not rows:
        return "No books yet. Put a book's PDF or EPUB in a course's Books folder, or its scans in Books/<title>/Scans."
    lines = []
    for b in rows:
        state = b["error"] or ("read" if b["total"] and b["done"] >= b["total"] else f"{b['done']} of {b['total'] or '?'} pages read so far")
        lines.append(f"{b['book']} ({b['course']}): {state}" + (f"; {b['poor']} pages are mostly equations or figures" if b["poor"] else ""))
    return "\n".join(lines)


def _reread_book(cfg, root) -> str:
    from tkinter import simpledialog

    from . import books

    title = simpledialog.askstring("Read a book again", "Which book? (its title or folder name)", parent=root)
    return books.reprocess(cfg, title) if title else "Nothing changed."


def _connect_canvas() -> str:
    from . import canvas_session, db

    with db.connect() as conn:
        return canvas_session.connect(conn)


def _disconnect_canvas() -> str:
    from . import canvas_session

    canvas_session.forget()
    return "Oso forgot your Canvas sign-in. Due dates still come from the calendar feed."


def _connect_calendar(cfg) -> str:
    from pathlib import Path

    from . import gcal

    path = filedialog.askopenfilename(title="Choose the OAuth client file from Google Cloud", filetypes=[("JSON", "*.json"), ("All files", "*")])
    if not path:
        return "No file chosen."
    try:
        gcal.connect(Path(path), cfg)
    except Exception as e:  # noqa: BLE001
        return f"Could not connect Google Calendar: {e}"
    return "Connected. Oso created a calendar named 'Oso' and will put urgent changes on it."


def _transcribe_now() -> str:
    from . import config as cfgmod
    from . import db, transcribe

    try:
        with db.connect() as conn:
            counts = transcribe.run(conn, cfgmod.load())
    except Exception as e:  # noqa: BLE001
        return f"Transcription failed: {e}"
    return f"Transcribed {counts['pages']} page(s) into {counts['notes']} note(s); {counts['low_confidence']} low confidence, {counts['failed']} failed."


def _sync_now() -> str:
    from . import config as cfgmod
    from . import sync

    try:
        results = sync.run(cfgmod.load())
    except Exception as e:  # noqa: BLE001
        return f"Sync failed: {e}"
    return "Synced.\n" + "\n".join(f"{k}: {v}" for k, v in results.items())
