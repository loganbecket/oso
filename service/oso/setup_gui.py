"""The setup window ("Set up Oso"): the whole setup, one step at a time, after the installer.

The installer is the only thing done in a command window; this window holds everything else, so the
student never has to work through the install guide. Each step says why it matters, then what to click,
with a button for each page it sends them to and for anything Oso can do itself. A few steps are needed
before Oso can run (the vault, the time zone, the Canvas calendar feed, the Canvas sign-in); everything
else can be marked done or skipped. Each step is recorded in the settings the moment it is done or
skipped, so closing the window loses nothing. Until every step is done or skipped, the Oso window offers
to resume setup each time it opens, and "Don't show this again" ends setup the same way finishing it does.
The install guide keeps every step in writing, for reference.
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk

from . import config as cfgmod
from . import secrets

log = logging.getLogger(__name__)

REPO = "loganbecket/oso"
TEMPLATE_URL = f"https://raw.githubusercontent.com/{REPO}/master/obsidian/web-clipper-template.json"
CLOUD = "https://console.cloud.google.com"

# (step, group in the side list, page title)
STEPS = [
    ("google_account", "Google", "A Google account"),
    ("g_project", "Google", "Register your own copy of Oso"),
    ("g_apis", "Google", "Turn on the three services"),
    ("g_app", "Google", "Name your app"),
    ("g_publish", "Google", "Publish it"),
    ("g_client", "Google", "Download the client file"),
    ("g_connect", "Google", "Connect email, calendar, and tasks"),
    ("google_drive", "Google", "Google Drive on this computer"),
    ("obsidian_install", "Obsidian", "Install Obsidian"),
    ("obsidian_vault", "Obsidian", "Make your vault"),
    ("folder", "Obsidian", "Choose your vault"),
    ("canvas_feed", "Canvas", "Your Canvas calendar"),
    ("canvas_sign_in", "Canvas", "Sign in to Canvas"),
    ("claude_pro", "Claude", "Claude Pro"),
    ("claude_apps", "Claude", "The Claude apps"),
    ("claude_code", "Claude", "Claude Code"),
    ("plugin", "Claude", "Add Oso to Claude"),
    ("claude_google", "Claude", "Google in Claude"),
    ("project", "Claude", "The School project"),
    ("web_clipper", "Obsidian add-ons", "The Web Clipper"),
    ("obsidian_plugins", "Obsidian add-ons", "Flashcards and course lists"),
    ("first_course", "Your first course", "Your first course"),
    ("groupme", "GroupMe", "GroupMe"),
    ("briefing", "Morning briefing", "The morning briefing"),
    ("chrome", "Claude in Chrome", "Claude in Chrome"),
    ("remarkable", "reMarkable tablet", "A reMarkable tablet"),
]
STEP_IDS = [s for s, _, _ in STEPS]
GROUPS = list(dict.fromkeys(g for _, g, _ in STEPS))
# Nothing else is worth doing until Oso can read the student's email: the Google account and its connection
# come first and can't be skipped, then the vault and Canvas.
REQUIRED = {"google_account", "g_project", "g_apis", "g_app", "g_publish", "g_client", "g_connect",
            "folder", "canvas_feed", "canvas_sign_in"}
BEFORE_FOLDER = STEP_IDS[:STEP_IDS.index("folder")]  # done before there are settings to record them in

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


def _windows() -> bool:
    return sys.platform == "win32"


def _mac() -> bool:
    return sys.platform == "darwin"


def _linux() -> bool:
    return sys.platform.startswith("linux")


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


def record(*steps: str) -> cfgmod.Config:
    """Mark steps done or skipped. Read fresh from disk each time: Claude may have added a course meanwhile."""
    cfg = cfgmod.load()
    for step in steps:
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


def begin(vault: Path, timezone: str, earlier: list[str] | tuple = ()) -> cfgmod.Config:
    """Choosing the vault: point Oso at it (made if missing) and save the time zone, keeping any settings
    already there, along with the steps done before there were settings to keep them in."""
    vault.mkdir(parents=True, exist_ok=True)
    try:
        cfg = cfgmod.load()
        cfg.vault, cfg.timezone = vault, timezone
    except cfgmod.ConfigError:
        cfg = cfgmod.Config(vault=vault, timezone=timezone, setup_finished=False)
    for sub in ("Clippings", "Courses", "Oso"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    cfgmod.save(cfg)
    return record(*earlier, "folder")


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
        if not name or "/" not in name:
            continue
        try:
            ZoneInfo(name)
        except Exception:  # noqa: BLE001, S112 - not a zone name; try the next
            continue
        return name
    return "America/New_York"


def save_template(folder: Path | None = None) -> str:
    """Put Oso's Web Clipper template in Downloads, for the clipper's Import button. A plain sentence back."""
    import urllib.request

    folder = folder or Path.home() / "Downloads"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(TEMPLATE_URL, timeout=20) as r:  # noqa: S310 - a fixed https address
            data = r.read()
        path = folder / "oso-web-clipper-template.json"
        path.write_bytes(data)
    except OSError as e:
        return f"Oso couldn't download the template ({getattr(e, 'reason', None) or e.strerror or e}). Check the internet connection and try again."
    return f"Saved the template as {path}."


def _app_name() -> str:
    if _windows():
        return "the Start menu (or press Ctrl+Alt+O)"
    return "your Applications folder" if _mac() else "the app menu"


def _command_window() -> str:
    if _windows():
        return "PowerShell (press the Windows key, type PowerShell, and press Enter)"
    return "Terminal (in Applications, then Utilities)" if _mac() else "a terminal"


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

        self.win = tk.Tk() if master is None else tk.Toplevel(master)
        self.win.title("Set up Oso")
        self.win.geometry("1000x680")
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
        self.earlier: list[str] = []  # steps done before the vault is chosen and there are settings to record them in

        body = ttk.Frame(self.win, padding=(12, 12, 32, 28))
        body.pack(fill="both", expand=True)
        self.sidebar = ttk.Frame(body, padding=(0, 0, 16, 0), width=250)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)  # the same width whichever step is in bold
        ttk.Separator(body, orient="vertical").pack(side="left", fill="y", padx=(0, 16))
        self.page = ttk.Frame(body)
        self.page.pack(side="left", fill="both", expand=True)

        left = remaining(self.cfg())
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

    def handled(self) -> set[str]:
        return (set(STEP_IDS) - set(remaining(self.cfg()))) | set(self.earlier)

    def close(self) -> None:
        self.polling = False
        self.win.destroy()
        if self.on_close:
            self.on_close()

    def draw_sidebar(self, current: int) -> None:
        for w in self.sidebar.winfo_children():
            w.destroy()
        handled = self.handled()
        here = STEPS[current][1] if current < len(STEPS) else None
        for group in GROUPS:
            pages = [(s, t) for s, g, t in STEPS if g == group]
            done = all(s in handled for s, _ in pages)
            row = ttk.Frame(self.sidebar)
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text="✓" if done else "•", foreground="#2e7d32" if done else "#999", width=2).pack(side="left")
            ttk.Label(row, text=group, font=self.bold if group == here else None,
                      foreground="#000" if group == here else "#444").pack(side="left")
            if group == here and len(pages) > 1:
                for s, t in pages:
                    sub = ttk.Frame(self.sidebar)
                    sub.pack(anchor="w", padx=(22, 0))
                    ttk.Label(sub, text="✓" if s in handled else "·", foreground="#2e7d32" if s in handled else "#999",
                              width=2).pack(side="left")
                    ttk.Label(sub, text=t, foreground="#000" if s == STEPS[current][0] else "#666").pack(side="left")

    def text(self, parent, words: str) -> ttk.Label:
        label = ttk.Label(parent, text=words, wraplength=640, justify="left")
        label.pack(anchor="w", pady=(0, 10))
        return label

    def why(self, parent, words: str) -> None:
        """What the step is for, set apart from the clicks."""
        ttk.Label(parent, text=words, wraplength=640, justify="left", foreground="#333").pack(anchor="w", pady=(0, 12))

    def steps(self, parent, *lines: str) -> None:
        self.text(parent, "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1)))

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
        step, group, title = STEPS[index]
        ttk.Label(self.page, text=title, font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 10))
        nav = ttk.Frame(self.page)
        nav.pack(side="bottom", fill="x", pady=(12, 0))
        self.message = ttk.Label(self.page, wraplength=640, justify="left", font=self.bold)
        self.message.pack(side="bottom", anchor="w", pady=(8, 0))
        content = ttk.Frame(self.page)
        content.pack(fill="both", expand=True, anchor="n")
        if index > 0:
            ttk.Button(nav, text="Back", command=lambda: self.show(index - 1)).pack(side="left")
        self.next_button = ttk.Button(nav, text="Next" if step in REQUIRED else "Done",
                                      command=lambda: self.advance(step))
        self.next_button.pack(side="right")
        if step not in REQUIRED or (step == "canvas_sign_in" and _linux()):
            ttk.Button(nav, text="Skip for now", command=lambda: self.advance(step)).pack(side="right", padx=8)
        getattr(self, f"page_{step}")(content)

    def advance(self, *steps: str) -> None:
        if self.cfg() is None:
            self.earlier += [s for s in steps if s not in self.earlier]
        else:
            try:
                record(*steps)
            except Exception as e:  # noqa: BLE001
                from .sync import plain_error

                self.say(f"Oso couldn't save that step: {plain_error(e)}")
                return
        later = [i for i, (s, _, _) in enumerate(STEPS) if s in steps]
        self.show(max(later) + 1)

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

    # -- Google

    def page_google_account(self, frame) -> None:
        self.why(frame, "Oso uses a Google account for email, calendar, tasks, and Drive. Your school email gets forwarded to "
                        "this account, so determine now if you want Oso integrated with your personal account or if you want to create a dedicated one that remains isolated. The decision comes down to personal preference and both choices are valid.")
        choice = tk.StringVar(value="new")
        sides = ttk.Frame(frame)
        sides.pack(anchor="w", fill="x")
        options = [
            ("new", "A new account just for Oso", [
                "Oso reads only school email, plus anything you forward to it.",
                "Any personal Google email, calendar, and Drive stay untouched.",
                "Oso's calendar and tasks live in this account; add it to your phone's Google apps to see them.",
                "One more account to sign in to.",
            ]),
            ("existing", "The account you already use", [
                "Oso reads your personal email too, so it catches activity outside your school email.",
                "Claude reads those messages in the background; you can tell Oso which senders to ignore.",
                "Oso's calendar and tasks show up in the apps you already use.",
                "Your notes share that account's Drive space.",
            ]),
        ]
        for col, (value, title, points) in enumerate(options):
            sides.columnconfigure(col, weight=1, uniform="sides")
            box = ttk.LabelFrame(sides, padding=10)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 12) if col == 0 else 0)
            # Tk's own radio button: round everywhere (the themed one is a diamond on Linux).
            bg = ttk.Style().lookup("TLabelframe", "background") or ttk.Style().lookup("TFrame", "background")
            tk.Radiobutton(box, text=title, value=value, variable=choice, command=lambda: make(), bg=bg, activebackground=bg,
                           highlightthickness=0, borderwidth=0, font=self.bold).pack(anchor="w", pady=(0, 6))
            for point in points:  # the bullet in its own column, so wrapped lines line up with the text
                line = ttk.Frame(box)
                line.pack(anchor="w", fill="x", pady=4)
                ttk.Label(line, text="•").pack(side="left", anchor="n", padx=(0, 6))
                ttk.Label(line, text=point, wraplength=280, justify="left").pack(side="left", anchor="n")
        after = ttk.Frame(frame)
        after.pack(anchor="w", fill="x", pady=(12, 0))

        def make() -> None:
            for w in after.winfo_children():
                w.destroy()
            if choice.get() == "new":
                self.steps(after, "Press Make a Google account and follow Google's steps.", "Come back and press Done.")
                self.link(after, "Make a Google account", "https://accounts.google.com/signup")

        make()

    def page_google_drive(self, frame) -> None:
        if _linux():
            self.why(frame, "Your vault lives in a folder synced with Google Drive, so your phone and Claude see your notes. "
                            "On Linux, rclone does the syncing.")
            self.steps(frame, "Press Install rclone and follow its steps.",
                       "In a terminal, run rclone config and add a Google Drive remote named gdrive.",
                       "Make a folder for your vault, such as ~/Vault.")
            self.link(frame, "Install rclone", "https://rclone.org/install/")
            return
        self.why(frame, "Your vault lives in your Google Drive folder, so your phone and Claude see your notes.")
        self.steps(frame, "Press Download Google Drive and install it.",
                   "Sign in with your Oso Google account. Stream or mirror both work.")
        self.link(frame, "Download Google Drive", "https://www.google.com/drive/download/")

    # -- Obsidian

    def page_obsidian_install(self, frame) -> None:
        self.why(frame, "Obsidian is the free notes app that holds everything Oso works from. Oso and Claude read and write "
                        "it for you.")
        self.steps(frame, "Press Download Obsidian and install it.")
        self.link(frame, "Download Obsidian", "https://obsidian.md/download")

    def page_obsidian_vault(self, frame) -> None:
        self.why(frame, "A vault is Obsidian's folder of notes. Make a new one for school, inside Google Drive.")
        place = "your rclone folder" if _linux() else "My Drive, in your Google Drive folder"
        self.steps(frame, "Open Obsidian. If a vault opens, click its name at the bottom left, then Manage vaults.",
                   "Next to Create new vault, click Create.",
                   f"Name it Vault, click Browse, choose {place}, and click Create.",
                   "Click the gear at the bottom left, then Community plugins, then Turn on community plugins.")

    def page_folder(self, frame) -> None:
        self.why(frame, "Tell Oso where your vault is.")
        cfg = self.cfg()
        vault_var = tk.StringVar(value=str(cfg.vault) if cfg else "")
        row = ttk.Frame(frame)
        row.pack(anchor="w", fill="x", pady=(0, 12))
        ttk.Entry(row, textvariable=vault_var, width=64).pack(side="left")
        ttk.Button(row, text="Choose…", command=lambda: vault_var.set(
            filedialog.askdirectory(parent=self.win, title="Choose your vault") or vault_var.get())).pack(side="left", padx=8)
        from .settings_gui import TIMEZONES

        ttk.Label(frame, text="Time zone").pack(anchor="w")
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
                begin(Path(raw).expanduser(), tz, self.earlier)
            except OSError as e:
                self.say(f"Oso couldn't use that folder ({e.strerror or e}). Choose another.")
                return
            self.earlier = []
            self.show(self.index + 1)

        self.next_button.configure(command=done)

    # -- Canvas

    def page_canvas_feed(self, frame) -> None:
        self.why(frame, "Canvas's private calendar feed is how Oso knows what's due.")
        self.steps(frame, "In Canvas, click Calendar, then Calendar Feed on the right.",
                   f"Copy the whole address and paste it here ({'Cmd' if _mac() else 'Ctrl'}+V).")
        have = bool(secrets.get(secrets.CANVAS_FEED_URL))
        if have:
            self.text(frame, "One is already saved; paste a new one only to replace it.")
        feed_var = tk.StringVar()
        ttk.Entry(frame, textvariable=feed_var, width=64, show="•").pack(anchor="w")

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
        if _linux():
            self.why(frame, "Canvas sign-in works only on Windows and macOS. Skip it; due dates still come from the feed.")
            self.next_button.configure(state="disabled")
            return
        self.why(frame, "Signing in adds grades, missing work, comments, files, and announcements.")
        self.steps(frame, "Press Sign in to Canvas and sign in as usual. The window closes itself when you're in.")
        from . import actions

        def sign_in() -> None:
            actions.connect_canvas()
            self.say("The Canvas sign-in window is opening.")

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

            threading.Thread(target=lambda: box.update(ok=signed_in()), daemon=True).start()
            self.win.after(300, wait)

        state.configure(text="Not signed in yet.")
        self.next_button.configure(state="disabled")
        self.polling = True
        check()

    # -- Claude

    def page_claude_pro(self, frame) -> None:
        self.why(frame, "Claude does Oso's thinking. Oso needs the Pro plan.")
        self.steps(frame, "Press Open claude.ai, sign in or make an account, and upgrade to Pro.",
                   "In Settings, under Privacy, turn off using your chats to improve Claude.")
        self.link(frame, "Open claude.ai", "https://claude.ai")

    def page_claude_apps(self, frame) -> None:
        self.why(frame, "You use Oso through the Claude app, on this computer and your phone.")
        if _linux():
            self.steps(frame, "On this computer, use Cowork at claude.ai in your browser.",
                       "On your phone, install Claude from the app store and sign in.")
            return
        self.steps(frame, "Press Download the Claude app, install it, and sign in.",
                   "Click Cowork in the sidebar once.",
                   "On your phone, install Claude from the app store and sign in.")
        self.link(frame, "Download the Claude app", "https://claude.ai/download")

    def page_claude_code(self, frame) -> None:
        self.why(frame, "Oso runs Claude Code in the background to read handwriting, email, and GroupMe.")
        if shutil.which("claude"):
            self.text(frame, "It's already installed. If you haven't signed in, type claude in "
                             f"{_command_window()} and sign in.")
            return
        self.steps(frame, "Press Open the Claude Code page and copy the install line for this computer.",
                   f"Paste it into {_command_window()} and press Enter.",
                   "In a new window, type claude, press Enter, and sign in.")
        self.link(frame, "Open the Claude Code page", "https://claude.ai/code")

    def page_plugin(self, frame) -> None:
        self.why(frame, "The plugin teaches Claude how to use Oso.")
        if _linux():
            self.steps(frame, "In a terminal, type claude and press Enter.",
                       f"Type /plugin marketplace add {REPO} and press Enter.",
                       "Type /plugin install oso@oso and press Enter.")
            return
        self.steps(frame, "Quit and reopen the Claude app.",
                   "Open Customize, then Plugins.",
                   f"Choose Add marketplace and enter {REPO}.",
                   "Install the Oso plugin, then turn on Sync automatically in the marketplace's menu.")

    def page_claude_google(self, frame) -> None:
        self.why(frame, "Claude reads your notes through Google Drive.")
        self.steps(frame, "In the Claude app, open Settings, then Connectors.",
                   "Connect Google Drive and Google Calendar with your Oso Google account.")

    def page_project(self, frame) -> None:
        if _linux():
            self.why(frame, "Claude works from your notes when it starts in your vault.")
            self.steps(frame, "Start Claude Code from inside your vault folder.")
            return
        self.why(frame, "Chats in a project work from your vault.")
        self.steps(frame, "In Cowork, click Projects and make one named School.",
                   "When it asks for a folder, choose your vault.",
                   "Start every study chat there.")

    # -- Obsidian add-ons

    def page_web_clipper(self, frame) -> None:
        self.why(frame, "The Web Clipper saves web pages, like a syllabus, into your vault.")
        self.steps(frame, "Press Get the Web Clipper, add it to your browser, and pick your vault.",
                   "Press Save Oso's template.",
                   "In the clipper, click the gear, then Templates, then Import, and pick that file from Downloads.")
        self.link(frame, "Get the Web Clipper", "https://obsidian.md/clipper")
        ttk.Button(frame, text="Save Oso's template", command=lambda: self.background("Downloading the template", save_template)).pack(
            anchor="w", pady=3)

    def page_obsidian_plugins(self, frame) -> None:
        self.why(frame, "Spaced Repetition shows Oso's flashcards. Dataview lists each course's notes.")
        self.steps(frame, "In Obsidian, click the gear, then Community plugins, then Browse.",
                   "Install and enable Spaced Repetition, then Dataview.")

    # -- courses

    def page_first_course(self, frame) -> None:
        self.why(frame, "Oso sets up a course from its syllabus.")
        self.steps(frame, "Clip the syllabus with the Web Clipper, or drop its PDF in your vault's Clippings folder.",
                   "In the School project, type /create-course and the course name.",
                   "Check what Claude found and confirm.")

    # -- Google Cloud

    def page_g_project(self, frame) -> None:
        self.why(frame, "Google lets only registered apps use your email, calendar, and tasks, so you register your own "
                        "private copy of Oso. It's free and takes about ten minutes.")
        self.steps(frame, "Press Open Google Cloud and sign in with your Oso Google account.",
                   "Click the project picker at the top, then New project.",
                   "Name it Oso, click Create, then select it in the project picker.")
        self.link(frame, "Open Google Cloud", CLOUD)

    def page_g_apis(self, frame) -> None:
        self.why(frame, "Turn on each service Oso uses.")
        self.steps(frame, "Press each button below and click Enable.")
        self.link(frame, "Google Calendar API", f"{CLOUD}/apis/library/calendar-json.googleapis.com")
        self.link(frame, "Gmail API", f"{CLOUD}/apis/library/gmail.googleapis.com")
        self.link(frame, "Google Tasks API", f"{CLOUD}/apis/library/tasks.googleapis.com")

    def page_g_app(self, frame) -> None:
        self.why(frame, "Google shows this name when Oso asks for access.")
        self.steps(frame, "Press Open Google Auth Platform and click Get started.",
                   "App name Oso, your email for support and contact, audience External.",
                   "Agree, then click Create.")
        self.link(frame, "Open Google Auth Platform", f"{CLOUD}/auth/overview")

    def page_g_publish(self, frame) -> None:
        self.why(frame, "Otherwise Google signs Oso out every seven days. It stays private.")
        self.steps(frame, "Press Open Audience, click Publish app, then Confirm.")
        self.link(frame, "Open Audience", f"{CLOUD}/auth/audience")

    def page_g_client(self, frame) -> None:
        self.why(frame, "This file lets Oso sign in as your app. Keep it private.")
        self.steps(frame, "Press Open Clients and click Create client.",
                   "Choose Desktop app, name it Oso, and click Create.",
                   "Click Download JSON.")
        self.link(frame, "Open Clients", f"{CLOUD}/auth/clients")

    def page_g_connect(self, frame) -> None:
        self.why(frame, "Google will say the app isn't verified, because it's your private copy. Click Advanced, then Go to "
                        "Oso.")
        self.steps(frame, "Forward your school email to your Oso Gmail.",
                   "Press Connect email and pick the file you downloaded.",
                   "Press Connect Google Calendar, then Connect Google Tasks.")
        from . import actions, gcal, mail, tasks
        from .settings_gui import _connect_calendar, _email_client_file

        def calendar() -> None:
            client = _email_client_file()
            if client is False:
                self.say("No file chosen.")
                return
            # The calendar is made in the student's time zone; before the vault is chosen that's the computer's.
            cfg = self.cfg() or cfgmod.Config(vault=Path.home(), timezone=local_timezone())
            self.background("Opening the Google sign-in in your browser", lambda: _connect_calendar(cfg, client))

        def google(connect) -> None:
            client = _email_client_file()
            if client is False:
                self.say("No file chosen.")
                return
            self.background("Opening the Google sign-in in your browser", lambda: connect(client))

        rows = {}
        for key, label, command in (("email", "Connect email…", lambda: google(actions.connect_email)),
                                    ("calendar", "Connect Google Calendar…", calendar),
                                    ("tasks", "Connect Google Tasks…", lambda: google(actions.connect_tasks))):
            row = ttk.Frame(frame)
            row.pack(anchor="w", pady=3)
            ttk.Button(row, text=label, command=command, width=26).pack(side="left")
            rows[key] = ttk.Label(row, text="Not connected yet.", foreground="#666")
            rows[key].pack(side="left", padx=10)

        def states() -> dict:
            out = {}
            for key, connected in (("email", mail.connected), ("calendar", gcal.connected), ("tasks", tasks.connected)):
                try:
                    out[key] = bool(connected())
                except Exception:  # noqa: BLE001
                    out[key] = False
            return out

        def check() -> None:
            if not self.polling or not self.win.winfo_exists():
                return
            box: dict = {}

            def wait() -> None:
                if not self.polling or not self.win.winfo_exists():
                    return
                if "states" not in box:
                    self.win.after(300, wait)
                    return
                for key, ok in box["states"].items():
                    rows[key].configure(text="Connected." if ok else "Not connected yet.", foreground="#2e7d32" if ok else "#666")
                if all(box["states"].values()):
                    self.next_button.configure(state="normal")
                else:
                    self.win.after(2000, check)

            threading.Thread(target=lambda: box.update(states=states()), daemon=True).start()
            self.win.after(300, wait)

        self.next_button.configure(state="disabled")
        self.polling = True
        check()

    # -- extras

    def page_groupme(self, frame) -> None:
        self.why(frame, "Only if you use GroupMe. Oso reads your groups for schedule changes.")
        self.steps(frame, "Press Open dev.groupme.com, sign in, and copy your Access Token (top right).",
                   "Press Connect GroupMe and paste it.")
        self.link(frame, "Open dev.groupme.com", "https://dev.groupme.com")
        from .settings_gui import _connect_groupme

        ttk.Button(frame, text="Connect GroupMe…", command=lambda: self.say(_connect_groupme(self.win))).pack(anchor="w", pady=3)

    def page_briefing(self, frame) -> None:
        self.why(frame, "A rundown of your day on your phone each morning, even with this computer off.")
        self.steps(frame, "In Cowork, make a scheduled task that runs daily when you wake up.",
                   "For its instruction, type: Run the oso-briefing skill.")

    def page_chrome(self, frame) -> None:
        self.why(frame, "Only for saving online textbook pages with /scrape-page.")
        self.steps(frame, "Press Open the Chrome extension, add it to Chrome, and sign in.")
        self.link(frame, "Open the Chrome extension", "https://claude.ai/chrome")

    def page_remarkable(self, frame) -> None:
        self.why(frame, "Only if you take notes on a reMarkable tablet.")
        self.steps(frame, "On the tablet, turn on Settings, Storage, USB web interface.",
                   "Make a folder for each course, named like its folder in your vault.",
                   "Plug the tablet in. Oso copies changed notebooks on its next check.")

    def finished_page(self) -> None:
        ttk.Label(self.page, text="You're set up", font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 12))
        self.text(self.page, f"Anything you skipped is on the Status tab of the Oso window, in {_app_name()}.")
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
    left = set(remaining(cfgmod.load()))
    groups = "\n".join(f"•  {g}" for g in GROUPS if any(s in left for s, gg, _ in STEPS if gg == g))
    ttk.Label(frame, text=f"Still to do:\n{groups}\n\nPick up where you left off?", wraplength=420, justify="left").pack(anchor="w")
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
