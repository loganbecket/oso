"""The setup window ("Set up Oso"): everything after the installer, one step at a time.

The installer opens it once. The first steps ask for what Oso can't run without (the vault, the time zone,
the Canvas calendar feed, the Canvas sign-in); the rest say what to do in Claude or elsewhere and can be
skipped. Each step is recorded in the settings the moment it is done or skipped, so closing the window
loses nothing. Until every step is done or skipped, the Oso window offers to resume setup each time it
opens, and "Don't show this again" ends setup the same way finishing it does.
"""

from __future__ import annotations

import logging
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from . import config as cfgmod
from . import secrets

log = logging.getLogger(__name__)

GUIDE = "https://github.com/loganbecket/oso/blob/master/docs/install.md"
REPO = "loganbecket/oso"

STEPS = [
    ("folder", "Your notes folder"),
    ("canvas_feed", "Canvas calendar"),
    ("canvas_sign_in", "Sign in to Canvas"),
    ("plugin", "Add Oso to Claude"),
    ("claude_google", "Google in Claude"),
    ("project", "The School project"),
    ("first_course", "Your first course"),
    ("google", "Calendar, email, and tasks"),
    ("groupme", "GroupMe"),
    ("briefing", "Morning briefing"),
    ("chrome", "Claude in Chrome"),
    ("remarkable", "reMarkable tablet"),
]
STEP_IDS = [s for s, _ in STEPS]
REQUIRED = {"folder", "canvas_feed", "canvas_sign_in"}

# Windows names its zones its own way; these cover the time zones in the settings list.
_WINDOWS_ZONES = {
    "Eastern Standard Time": "America/New_York", "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver", "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles", "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu", "GMT Standard Time": "Europe/London",
    "Romance Standard Time": "Europe/Paris", "W. Europe Standard Time": "Europe/Berlin",
    "Tokyo Standard Time": "Asia/Tokyo", "China Standard Time": "Asia/Shanghai",
    "India Standard Time": "Asia/Kolkata", "AUS Eastern Standard Time": "Australia/Sydney",
}


# ---- what is done ------------------------------------------------------------------------------------


def needs_setup() -> bool:
    """True before the vault is chosen, and until every step is done or skipped."""
    try:
        return not cfgmod.load().setup_finished
    except cfgmod.ConfigError:
        return True


def remaining(cfg: cfgmod.Config | None) -> list[str]:
    if cfg is None:
        return list(STEP_IDS)
    if cfg.setup_finished:
        return []
    return [s for s in STEP_IDS if s not in cfg.setup_steps]


def record(step: str) -> cfgmod.Config:
    """Mark a step done or skipped. Read fresh from disk each time: Claude may have added a course meanwhile."""
    cfg = cfgmod.load()
    if not cfg.setup_finished and step not in cfg.setup_steps:
        cfg.setup_steps.append(step)
    if not remaining(cfg):
        cfg.setup_finished, cfg.setup_steps = True, []
    cfgmod.save(cfg)
    return cfg


def stop_showing() -> cfgmod.Config:
    """"Don't show this again": setup is over, the same as if every step were done or skipped."""
    cfg = cfgmod.load()
    cfg.setup_finished, cfg.setup_steps = True, []
    cfgmod.save(cfg)
    return cfg


def begin(vault: Path, timezone: str) -> cfgmod.Config:
    """The first step: point Oso at the vault (made if missing) and save the time zone, keeping any
    settings already there."""
    vault.mkdir(parents=True, exist_ok=True)
    try:
        cfg = cfgmod.load()
        cfg.vault, cfg.timezone = vault, timezone
    except cfgmod.ConfigError:
        cfg = cfgmod.Config(vault=vault, timezone=timezone, setup_finished=False)
    for sub in ("Clippings", "Courses", "Oso"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    cfgmod.save(cfg)
    return record("folder")


def local_timezone() -> str:
    """This computer's time zone as a name Oso understands, or US Eastern when it can't tell."""
    import os
    import time
    from zoneinfo import ZoneInfo

    candidates = [os.environ.get("TZ", "")]
    try:
        target = str(Path("/etc/localtime").resolve())
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    candidates.append(_WINDOWS_ZONES.get(time.tzname[0], ""))
    for name in candidates:
        if name and "/" in name:
            try:
                ZoneInfo(name)
                return name
            except Exception:  # noqa: BLE001 - not a zone name; try the next
                continue
    return "America/New_York"


def _app_name() -> str:
    return {"win32": "the Start menu (or press Ctrl+Alt+O)", "darwin": "your Applications folder"}.get(sys.platform, "the app menu")


def _start_checking(cfg: cfgmod.Config) -> None:
    """Schedule the automatic check and run a first one, so Oso is working even if setup is left half done."""
    from . import actions
    from .settings_gui import _reschedule

    try:
        _reschedule(cfg.sync_interval_minutes)
        actions._start("sync")
    except Exception:  # the installer schedules it again when the window closes
        log.exception("could not schedule the check from setup")


# ---- the window ------------------------------------------------------------------------------------


def run(master: tk.Misc | None = None, on_close=None) -> None:
    """Open the setup window: on its own (from the installer), or over the Oso window when master is given."""
    Wizard(master, on_close)
    if master is None:
        tk.mainloop()


class Wizard:
    def __init__(self, master: tk.Misc | None, on_close=None):
        from tkinter import font as tkfont

        from .settings_gui import _brand

        self.standalone = master is None
        self.win = tk.Tk() if master is None else tk.Toplevel(master)
        self.win.title("Set up Oso")
        self.win.geometry("900x600")
        self.on_close = on_close
        _brand(self.win)
        if master is not None:
            self.win.transient(master)
            self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.bold = tkfont.nametofont("TkDefaultFont").copy()
        self.bold.configure(weight="bold")
        self.started_checking = False
        self.polling = False

        body = ttk.Frame(self.win, padding=12)
        body.pack(fill="both", expand=True)
        self.sidebar = ttk.Frame(body, padding=(0, 0, 16, 0), width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)  # the same width whichever step is in bold
        ttk.Separator(body, orient="vertical").pack(side="left", fill="y", padx=(0, 16))
        self.page = ttk.Frame(body)
        self.page.pack(side="left", fill="both", expand=True)

        try:
            cfg = cfgmod.load()
        except cfgmod.ConfigError:
            cfg = None
        left = remaining(cfg)
        self.show(STEP_IDS.index(left[0]) if left else len(STEPS))
        # In front of the command window the installer runs in.
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.after(300, lambda: self.win.winfo_exists() and self.win.attributes("-topmost", False))
        self.win.focus_force()

    # -- helpers

    def cfg(self) -> cfgmod.Config | None:
        try:
            return cfgmod.load()
        except cfgmod.ConfigError:
            return None

    def close(self) -> None:
        self.polling = False
        self.win.destroy()
        if self.on_close:
            self.on_close()

    def draw_sidebar(self, current: int) -> None:
        for w in self.sidebar.winfo_children():
            w.destroy()
        cfg = self.cfg()
        handled = set(STEP_IDS) - set(remaining(cfg))
        for i, (step, title) in enumerate(STEPS):
            mark, color = ("✓", "#2e7d32") if step in handled else ("•", "#999")
            row = ttk.Frame(self.sidebar)
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text=mark, foreground=color, width=2).pack(side="left")
            ttk.Label(row, text=title, font=self.bold if i == current else None,
                      foreground="#000" if i == current else "#444").pack(side="left")

    def text(self, parent, words: str) -> ttk.Label:
        label = ttk.Label(parent, text=words, wraplength=560, justify="left")
        label.pack(anchor="w", pady=(0, 10))
        return label

    def link(self, parent, label: str, url: str) -> None:
        ttk.Button(parent, text=label, command=lambda: webbrowser.open(url)).pack(anchor="w", pady=3)

    def show(self, index: int) -> None:
        self.polling = False
        self.index = index
        for w in self.page.winfo_children():
            w.destroy()
        self.draw_sidebar(index)
        if index >= len(STEPS):
            self.finished_page()
            return
        step, title = STEPS[index]
        ttk.Label(self.page, text=title, font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 12))
        nav = ttk.Frame(self.page)
        nav.pack(side="bottom", fill="x", pady=(12, 0))
        self.message = ttk.Label(self.page, wraplength=560, justify="left", font=self.bold)
        self.message.pack(side="bottom", anchor="w", pady=(8, 0))
        content = ttk.Frame(self.page)
        content.pack(fill="both", expand=True, anchor="n")
        if index > 0:
            ttk.Button(nav, text="Back", command=lambda: self.show(index - 1)).pack(side="left")
        self.next_button = ttk.Button(nav, text="Next" if step in REQUIRED else "Done")
        self.next_button.pack(side="right")
        if step not in REQUIRED or (step == "canvas_sign_in" and sys.platform.startswith("linux")):
            ttk.Button(nav, text="Skip for now", command=lambda: self.advance(step)).pack(side="right", padx=8)
        getattr(self, f"page_{step}")(content)

    def advance(self, step: str) -> None:
        try:
            record(step)
        except Exception as e:  # noqa: BLE001
            from .sync import plain_error

            self.say(f"Oso couldn't save that step: {plain_error(e)}")
            return
        self.show(self.index + 1)

    def say(self, words: str) -> None:
        self.message.configure(text=words)

    def background(self, label: str, fn) -> None:
        """Run a connection without freezing the window, then show its sentence."""
        from .settings_gui import _safe

        self.say(f"{label}…")
        box: dict = {}
        threading.Thread(target=lambda: box.update(text=_safe(fn)), daemon=True).start()

        def wait() -> None:
            if not self.win.winfo_exists():
                return
            if "text" in box:
                self.say(box["text"])
            else:
                self.win.after(300, wait)

        self.win.after(300, wait)

    # -- the steps

    def page_folder(self, frame) -> None:
        where = ("the folder rclone keeps in sync with Google Drive" if sys.platform.startswith("linux")
                 else "inside your Google Drive folder")
        self.text(frame, f"Pick the vault you made in Obsidian. It should be {where}, so your phone and Claude see the same notes.")
        cfg = self.cfg()
        vault_var = tk.StringVar(value=str(cfg.vault) if cfg else "")
        row = ttk.Frame(frame)
        row.pack(anchor="w", fill="x", pady=(0, 12))
        ttk.Entry(row, textvariable=vault_var, width=60).pack(side="left")
        ttk.Button(row, text="Choose…", command=lambda: vault_var.set(
            filedialog.askdirectory(parent=self.win, title="Choose your vault") or vault_var.get())).pack(side="left", padx=8)
        self.text(frame, "Your time zone, so due dates and reminders land at the right hour:")
        from .settings_gui import TIMEZONES

        tz_var = tk.StringVar(value=cfg.timezone if cfg else local_timezone())
        ttk.Combobox(frame, textvariable=tz_var, values=TIMEZONES, width=30).pack(anchor="w")

        def done() -> None:
            from zoneinfo import ZoneInfo

            raw = vault_var.get().strip().strip('"')
            if not raw:
                self.say("Choose your vault folder first.")
                return
            tz = tz_var.get().strip()
            try:
                ZoneInfo(tz)
            except Exception:  # noqa: BLE001
                self.say(f"{tz or 'That'} isn't a time zone Oso knows. Pick one from the list.")
                return
            try:
                begin(Path(raw).expanduser(), tz)
            except OSError as e:
                self.say(f"Oso couldn't use that folder ({e.strerror or e}). Choose another.")
                return
            self.show(self.index + 1)

        self.next_button.configure(command=done)

    def page_canvas_feed(self, frame) -> None:
        self.text(frame, "Oso reads your due dates from Canvas's calendar feed. In Canvas, click Calendar in the left menu, then "
                         "Calendar Feed on the right, and copy the whole address (it starts with https:// and ends in .ics). "
                         "Treat it like a password: anyone with it can see your calendar.")
        have = bool(secrets.get(secrets.CANVAS_FEED_URL))
        if have:
            self.text(frame, "A feed address is already saved. Paste a new one only to replace it.")
        feed_var = tk.StringVar()
        ttk.Entry(frame, textvariable=feed_var, width=60, show="•").pack(anchor="w")

        def done() -> None:
            url = feed_var.get().strip()
            if not url and not have:
                self.say("Paste the Calendar Feed address first.")
                return
            if url and not url.lower().startswith(("https://", "http://", "webcal://")):
                self.say("That doesn't look like the Calendar Feed address. It starts with https:// and ends in .ics.")
                return
            if url:
                secrets.set(secrets.CANVAS_FEED_URL, url)
            first = "canvas_feed" in remaining(self.cfg())
            cfg = record("canvas_feed")
            if first and not self.started_checking:
                self.started_checking = True
                threading.Thread(target=_start_checking, args=(cfg,), daemon=True).start()
            self.show(self.index + 1)

        self.next_button.configure(command=done)

    def page_canvas_sign_in(self, frame) -> None:
        if sys.platform.startswith("linux"):
            self.text(frame, "Signing in to Canvas works only on Windows and macOS. Skip this for now; due dates still come in "
                             "from the calendar feed.")
            self.next_button.configure(state="disabled")
            return
        self.text(frame, "Signing in lets Oso read your grades, scores, missing work, instructor comments, course files, and "
                         "announcements. A small window opens with your school's Canvas sign-in page. Sign in as usual, including "
                         "any two-step check; the window closes by itself once you're in.")
        from . import actions

        def sign_in() -> None:
            actions.connect_canvas()
            self.say("The Canvas sign-in window is opening. This step ticks itself off once you're in.")

        ttk.Button(frame, text="Sign in to Canvas", command=sign_in).pack(anchor="w")
        state = ttk.Label(frame, foreground="#666")
        state.pack(anchor="w", pady=(10, 0))

        def signed_in() -> bool:
            from . import canvas_session, db

            try:
                with db.connect() as conn:
                    return canvas_session.status(conn) == "connected"
            except Exception:  # noqa: BLE001
                return False

        def check() -> None:
            if not self.polling or not self.win.winfo_exists():
                return
            box: dict = {}

            def look() -> None:
                box["ok"] = signed_in()

            def wait() -> None:
                if not self.polling or not self.win.winfo_exists():
                    return
                if "ok" not in box:
                    self.win.after(300, wait)
                    return
                if box["ok"]:
                    state.configure(text="Signed in.", foreground="#2e7d32")
                    self.next_button.configure(state="normal")
                else:
                    self.win.after(2000, check)

            threading.Thread(target=look, daemon=True).start()
            self.win.after(300, wait)

        state.configure(text="Not signed in yet.")
        self.next_button.configure(state="disabled", command=lambda: self.advance("canvas_sign_in"))
        self.polling = True
        check()

    def page_plugin(self, frame) -> None:
        if sys.platform.startswith("linux"):
            self.text(frame, "The plugin teaches Claude how to use Oso. Start Claude Code (type claude in a terminal) and enter "
                             f"these two lines:\n\n/plugin marketplace add {REPO}\n/plugin install oso@oso")
        else:
            self.text(frame, "The plugin teaches Claude how to use Oso. If the Claude app was open while Oso installed, quit it and "
                             "open it again first. Then, in the Claude app:\n\n"
                             "1. In the sidebar, open Customize, then Plugins.\n"
                             f"2. Choose Add marketplace and enter {REPO}.\n"
                             "3. Click Install on the Oso plugin.\n"
                             "4. Open the Oso marketplace's menu and turn on Sync automatically, so the plugin keeps itself up to date.")
        self.next_button.configure(command=lambda: self.advance("plugin"))

    def page_claude_google(self, frame) -> None:
        self.text(frame, "In the Claude app (or claude.ai), open Settings, then Connectors. Connect Google Drive, Google Calendar, "
                         "and Gmail, signing in with your Google account each time.\n\n"
                         "Drive is the one Claude needs to see your notes; Calendar lets Claude put study blocks on your calendar; "
                         "Gmail is optional.")
        self.next_button.configure(command=lambda: self.advance("claude_google"))

    def page_project(self, frame) -> None:
        if sys.platform.startswith("linux"):
            self.text(frame, "In Claude Code, start every study chat from inside your vault folder, so Claude works with your notes.")
        else:
            self.text(frame, "In Cowork, click Projects in the sidebar and make a project named School. When it asks for a folder, "
                             "pick your vault. Start every study chat inside this project.")
        self.next_button.configure(command=lambda: self.advance("project"))

    def page_first_course(self, frame) -> None:
        self.text(frame, "Oso sets up each course from its syllabus.\n\n"
                         "1. Open the syllabus in your browser and save it with the Obsidian Web Clipper, or put the syllabus PDF "
                         "in your vault's Clippings folder.\n"
                         "2. In a chat in the School project, type /create-course and the course name, for example "
                         "/create-course Intro to Engineering.\n"
                         "3. Check the dates, grade weights, and class times Claude shows you, fix anything wrong, and confirm.\n\n"
                         "Do one now; the rest can wait. Repeat it for each course.")
        self.next_button.configure(command=lambda: self.advance("first_course"))

    def page_google(self, frame) -> None:
        self.text(frame, "Oso can keep its own Google calendar (your classes, urgent changes, reminders), read the Gmail account your "
                         "school email is forwarded to, and keep your tasks in Google Tasks on your phone. Google needs a one-time "
                         "setup for this, about ten minutes: open the instructions, follow them to download a client file, then "
                         "connect each one below.")
        self.link(frame, "Open the instructions", f"{GUIDE}#the-oso-calendar")
        from . import actions
        from .settings_gui import _connect_calendar, _email_client_file

        def calendar() -> None:
            path = filedialog.askopenfilename(parent=self.win, title="Choose the OAuth client file from Google Cloud",
                                              filetypes=[("JSON", "*.json"), ("All files", "*")])
            if not path:
                self.say("No file chosen.")
                return
            cfg = self.cfg()
            self.background("Connecting Google Calendar (sign in in your browser)", lambda: _connect_calendar(cfg, Path(path)))

        def google(connect, label) -> None:
            client = _email_client_file()
            if client is False:
                self.say("No file chosen.")
                return
            self.background(label, lambda: connect(client))

        ttk.Button(frame, text="Connect Google Calendar…", command=calendar).pack(anchor="w", pady=3)
        ttk.Button(frame, text="Connect email…", command=lambda: google(actions.connect_email, "Opening the Google sign-in")).pack(anchor="w", pady=3)
        ttk.Button(frame, text="Connect Google Tasks…", command=lambda: google(actions.connect_tasks, "Opening the Google sign-in")).pack(anchor="w", pady=3)
        self.next_button.configure(command=lambda: self.advance("google"))

    def page_groupme(self, frame) -> None:
        self.text(frame, "Only if your classes use GroupMe. Sign in at dev.groupme.com, click Access Token at the top right, and "
                         "copy it. Then press Connect GroupMe and paste it.")
        self.link(frame, "Open dev.groupme.com", "https://dev.groupme.com")
        from .settings_gui import _connect_groupme

        ttk.Button(frame, text="Connect GroupMe…", command=lambda: self.say(_connect_groupme(self.win))).pack(anchor="w", pady=3)
        self.next_button.configure(command=lambda: self.advance("groupme"))

    def page_briefing(self, frame) -> None:
        self.text(frame, "In Cowork, make a scheduled task that runs every day at the time you wake up, with this instruction:\n\n"
                         "Run the oso-briefing skill.\n\n"
                         "The briefing shows up in the Claude app on your phone. It runs in Claude's cloud, so it comes even when "
                         "this computer is off.")
        self.next_button.configure(command=lambda: self.advance("briefing"))

    def page_chrome(self, frame) -> None:
        self.text(frame, "Only needed to save online textbook pages into a course's book with /scrape-page. Install the Claude "
                         "extension from the Chrome Web Store and sign in with your Claude account. The first time you save "
                         "pages from a site, allow Claude to read that site when the extension asks.")
        self.link(frame, "Open the Chrome extension", "https://claude.ai/chrome")
        self.next_button.configure(command=lambda: self.advance("chrome"))

    def page_remarkable(self, frame) -> None:
        self.text(frame, "Only if you take notes on a reMarkable tablet; photographed or scanned paper notes work without it.\n\n"
                         "1. On the tablet, open Settings, then Storage, and turn on USB web interface.\n"
                         "2. Make a folder on the tablet for each course, named exactly like the course's folder in your vault.\n"
                         "3. Plug the tablet into this computer with its cable. Oso copies notebooks you changed on its next check.")
        self.link(frame, "Open the instructions", f"{GUIDE}#your-remarkable-tablet")
        self.next_button.configure(command=lambda: self.advance("remarkable"))

    def finished_page(self) -> None:
        ttk.Label(self.page, text="You're set up", font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 12))
        self.text(self.page, "Oso checks for changes every 15 minutes from now on. Anything you skipped is on the Status tab of the "
                             f"Oso window, which opens from {_app_name()}, or when you ask Claude to open your settings.")
        nav = ttk.Frame(self.page)
        nav.pack(side="bottom", fill="x")
        ttk.Button(nav, text="Close", command=self.close).pack(side="right")
        ttk.Button(nav, text="Back", command=lambda: self.show(len(STEPS) - 1)).pack(side="left")


# ---- the reminder in the Oso window ------------------------------------------------------------------


def offer_resume(root: tk.Misc, on_done) -> None:
    """The box that comes up over the Oso window while setup isn't finished."""
    box = tk.Toplevel(root)
    box.title("Setup isn't finished")
    box.transient(root)
    box.resizable(False, False)
    frame = ttk.Frame(box, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Setup isn't finished", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 8))
    left = remaining(cfgmod.load())
    titles = ", ".join(t for s, t in STEPS if s in left)
    ttk.Label(frame, text=f"Still to do: {titles}.\n\nPick up where you left off?", wraplength=420, justify="left").pack(anchor="w")
    never = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text="Don't show this again", variable=never).pack(anchor="w", pady=(12, 0))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(16, 0))

    def resume() -> None:
        box.destroy()
        run(root, on_close=on_done)

    def not_now() -> None:
        if never.get():
            stop_showing()
        box.destroy()
        on_done()

    ttk.Button(buttons, text="Resume setup", command=resume).pack(side="right")
    ttk.Button(buttons, text="Not now", command=not_now).pack(side="right", padx=8)
    box.protocol("WM_DELETE_WINDOW", not_now)
    box.update_idletasks()
    x = root.winfo_rootx() + max(0, (root.winfo_width() - box.winfo_reqwidth()) // 2)
    y = root.winfo_rooty() + max(0, (root.winfo_height() - box.winfo_reqheight()) // 3)
    box.geometry(f"+{x}+{y}")
    box.lift()
    box.focus_force()
    box.grab_set()
