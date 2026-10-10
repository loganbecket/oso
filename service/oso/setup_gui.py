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

GOOGLE_CLOUD = "Calendar, email, and tasks"

# (step, group in the side list, page title)
STEPS = [
    ("google_account", "Google", "A Google account"),
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
    ("g_project", GOOGLE_CLOUD, "Register your own copy of Oso"),
    ("g_apis", GOOGLE_CLOUD, "Turn on the three services"),
    ("g_app", GOOGLE_CLOUD, "Name your app"),
    ("g_publish", GOOGLE_CLOUD, "Publish it"),
    ("g_client", GOOGLE_CLOUD, "Download the client file"),
    ("g_connect", GOOGLE_CLOUD, "Connect them"),
    ("groupme", "GroupMe", "GroupMe"),
    ("briefing", "Morning briefing", "The morning briefing"),
    ("chrome", "Claude in Chrome", "Claude in Chrome"),
    ("remarkable", "reMarkable tablet", "A reMarkable tablet"),
]
STEP_IDS = [s for s, _, _ in STEPS]
GROUPS = list(dict.fromkeys(g for _, g, _ in STEPS))
REQUIRED = {"folder", "canvas_feed", "canvas_sign_in"}
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

        body = ttk.Frame(self.win, padding=12)
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
        if step == "g_project":
            rest = [s for s, g, _ in STEPS if g == GOOGLE_CLOUD]
            ttk.Button(nav, text="Skip all of these", command=lambda: self.advance(*rest)).pack(side="right")
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
        self.why(frame, "Oso uses Google for three things: Google Drive carries your notes to your phone and to Claude, Google "
                        "Calendar holds your classes and reminders, and Google Tasks keeps your to-do list on your phone.")
        self.text(frame, "If you have a Gmail address, you're set: press Done. A Google account from your school works too.\n\n"
                         "If you don't have one:")
        self.steps(frame, "Press Make a Google account.",
                   "Follow Google's steps to choose your name, a Gmail address, and a password.",
                   "Come back here and press Done.")
        self.link(frame, "Make a Google account", "https://accounts.google.com/signup")

    def page_google_drive(self, frame) -> None:
        if _linux():
            self.why(frame, "Your notes live in a folder that Google Drive keeps in sync, so your phone and Claude see the same "
                            "notes this computer does. Google doesn't make Drive for Linux, so rclone does the syncing.")
            self.steps(frame, "Press Install rclone and follow the instructions for your system.",
                       "In a terminal, run rclone config and add a Google Drive remote named gdrive.",
                       "Make a folder for your vault, for example Vault in your home folder.",
                       "When setup closes, the installer offers to keep that folder in sync with Drive every 15 minutes.")
            self.link(frame, "Install rclone", "https://rclone.org/install/")
            return
        self.why(frame, "Your notes live in a folder that Google Drive keeps in sync, so your phone and Claude's morning "
                        "briefing see the same notes this computer does.")
        where = (r"It shows up in File Explorer as a drive named Google Drive, usually G:, with My Drive inside "
                 r"(sometimes it's C:\Users\<you>\My Drive instead)." if _windows()
                 else "It shows up in Finder's sidebar under Locations as Google Drive, with My Drive inside.")
        self.steps(frame, "Press Download Google Drive, then download Drive for desktop.",
                   "Open the file you downloaded and install it.",
                   "Sign in with your Google account.",
                   "If it asks whether to stream or mirror your files, either one works.",
                   f"Drive now has a folder on this computer. {where}")
        self.text(frame, "If Google Drive is already on this computer, press Done.")
        self.link(frame, "Download Google Drive", "https://www.google.com/drive/download/")

    # -- Obsidian

    def page_obsidian_install(self, frame) -> None:
        self.why(frame, "Obsidian is a free notes app, and it's where everything Oso works from lives: your syllabi, notes, "
                        "readings, and the notes Oso writes for you. Oso and Claude read and write it for you, so you don't have "
                        "to open it day to day.")
        self.text(frame, "If Obsidian is already on this computer, press Done. Otherwise:")
        self.steps(frame, "Press Download Obsidian, and download the version for this computer.",
                   "Open the file you downloaded and install it.")
        self.link(frame, "Download Obsidian", "https://obsidian.md/download")

    def page_obsidian_vault(self, frame) -> None:
        self.why(frame, "A vault is the folder where Obsidian keeps your notes. Putting it inside your Google Drive folder is "
                        "what lets Claude, including the Claude app on your phone, see your notes.")
        place = "the folder you made for rclone" if _linux() else "My Drive, inside your Google Drive folder"
        self.steps(frame, "Open Obsidian. If it opens straight into a vault you already have, click that vault's name at the "
                          "bottom left and choose Manage vaults.",
                   "Next to Create new vault, click Create.",
                   "For the vault name, type Vault.",
                   f"For the location, click Browse and choose {place}.",
                   "Click Create. Obsidian opens your new, empty vault.",
                   "Click the gear at the bottom left to open Settings, choose Community plugins, and click Turn on "
                   "community plugins. Oso's add-ons need this later. Close Settings.")
        self.text(frame, "Already use Obsidian for something else? Make a new vault for school anyway; Oso adds folders and "
                         "notes of its own.")

    def page_folder(self, frame) -> None:
        self.why(frame, "Now tell Oso where that vault is. Oso files your course material there and reads it for everything "
                        "it does.")
        cfg = self.cfg()
        self.steps(frame, "Click Choose and pick the Vault folder you just made.",
                   "Check your time zone below, so due dates and reminders land at the right hour.",
                   "Press Next.")
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
        self.why(frame, "Canvas is your school's course website. Every Canvas account has a private calendar feed listing "
                        "everything that's due, and that's how Oso knows your deadlines.")
        self.steps(frame, "Sign in to Canvas in your browser.",
                   "Click Calendar in the menu on the left.",
                   "On the right side of the calendar, click Calendar Feed.",
                   "A box shows a long address that starts with https:// and ends in .ics. Copy all of it.",
                   f"Paste it below ({'Cmd' if _mac() else 'Ctrl'}+V) and press Next.")
        self.text(frame, "Treat the address like a password: anyone who has it can see your calendar. Oso keeps it in this "
                         "computer's credential store, never in a file.")
        have = bool(secrets.get(secrets.CANVAS_FEED_URL))
        if have:
            self.text(frame, "A feed address is already saved. Paste a new one only to replace it.")
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
            self.why(frame, "Signing in to Canvas lets Oso read your grades and coursework, but it works only on Windows and "
                            "macOS. Skip this for now; due dates still come in from the calendar feed.")
            self.next_button.configure(state="disabled")
            return
        self.why(frame, "The calendar feed only has due dates. Signing in lets Oso also read your grades, scores, missing "
                        "work, instructor comments, course files, and announcements.")
        self.steps(frame, "Press Sign in to Canvas. A small window opens with your school's Canvas sign-in page.",
                   "Sign in as usual, including any two-step check like Duo.",
                   "The window closes by itself once you're in, and this step ticks itself off.")
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
        self.why(frame, "Claude does the thinking: answering your questions, writing study guides and practice tests, reading "
                        "your handwriting. Oso needs the Pro plan for Cowork (where you study), scheduled tasks (the morning "
                        "briefing), and Claude Code.")
        self.steps(frame, "Press Open claude.ai and sign in, or make an account.",
                   "Upgrade to the Pro plan. If it isn't offered right away, open Settings, then Billing.",
                   "In Settings, find the Privacy section and turn off the option that lets your chats be used to improve "
                   "Claude's models. Your coursework stays yours.")
        self.text(frame, "Already on Pro? Just check the privacy setting, then press Done.")
        self.link(frame, "Open claude.ai", "https://claude.ai")

    def page_claude_apps(self, frame) -> None:
        self.why(frame, "You talk to Oso through the Claude app: on this computer to study, and on your phone for the morning "
                        "briefing and quick questions.")
        if _linux():
            self.steps(frame, "There's no Claude desktop app for Linux: use Cowork at claude.ai in your browser.",
                       "On your phone, install Claude from the App Store or Google Play and sign in with the same account.")
        else:
            self.steps(frame, "Press Download the Claude app. Open the file you downloaded, install it, and sign in.",
                       "Click Cowork in the app's sidebar once, so it gets set up.",
                       "On your phone, install Claude from the App Store or Google Play and sign in with the same account.")
            self.link(frame, "Download the Claude app", "https://claude.ai/download")

    def page_claude_code(self, frame) -> None:
        self.why(frame, "Claude Code is Claude in a command window. Oso runs it in the background, out of sight, to read your "
                        "handwritten notes, your school email, and GroupMe, and to act on your rules. You won't have to use it "
                        "yourself.")
        if shutil.which("claude"):
            self.text(frame, "Claude Code is already installed on this computer. If you haven't signed in to it yet, open "
                             f"{_command_window()}, type claude, press Enter, and sign in when it asks. Then press Done.")
            return
        self.steps(frame, "Press Open the Claude Code page and find the install line for this computer"
                          f"{' (the one for PowerShell)' if _windows() else ''}. Copy it.",
                   f"Open {_command_window()}, paste the line, and press Enter.",
                   "When it finishes, close that window, open a new one, type claude, and press Enter.",
                   "Sign in with your Claude account when it asks, then type /exit and press Enter.")
        self.link(frame, "Open the Claude Code page", "https://claude.ai/code")

    def page_plugin(self, frame) -> None:
        self.why(frame, "The Oso plugin teaches Claude how to use Oso: your deadlines, your notes, quizzes, and every Oso "
                        "command.")
        if _linux():
            self.steps(frame, "Open a terminal, type claude, and press Enter.",
                       f"Type /plugin marketplace add {REPO} and press Enter.",
                       "Type /plugin install oso@oso and press Enter.")
            return
        self.steps(frame, "If the Claude app was open while Oso installed, quit it completely and open it again.",
                   "In the Claude app's sidebar, open Customize, then Plugins.",
                   f"Choose Add marketplace, type {REPO}, and confirm.",
                   "The Oso plugin appears. Click Install.",
                   "On the same page, open the Oso marketplace's menu and turn on Sync automatically, so the plugin keeps "
                   "itself up to date.")
        self.text(frame, "The plugin's Connectors tab lists an oso connector as \"Runs in each session\". There's nothing to "
                         "click there; don't use Add custom connector.")

    def page_claude_google(self, frame) -> None:
        self.why(frame, "Claude reaches your notes through Google Drive, the same copy your phone sees. Calendar lets Claude "
                        "put study blocks on your calendar.")
        self.steps(frame, "In the Claude app (or claude.ai), open Settings, then Connectors.",
                   "Find Google Drive and click Connect. Sign in with your Google account and allow access.",
                   "Do the same for Google Calendar.",
                   "Gmail is optional; connect it too if you'd like Claude to search your email when you ask.")

    def page_project(self, frame) -> None:
        if _linux():
            self.why(frame, "Claude works from your notes when it starts inside your vault.")
            self.steps(frame, "Whenever you study with Claude Code, open a terminal in your vault folder first, then type claude.")
            return
        self.why(frame, "A project gives every chat inside it your vault, so Claude works from your notes instead of from "
                        "memory.")
        self.steps(frame, "In the Claude app, open Cowork and click Projects in the sidebar.",
                   "Make a new project and name it School.",
                   "When it asks for a folder, choose your vault.",
                   "From now on, start every study chat inside the School project.")

    # -- Obsidian add-ons

    def page_web_clipper(self, frame) -> None:
        self.why(frame, "The Web Clipper saves a web page into your vault with one click: syllabi, articles, papers. It's how "
                        "you'll set up your courses in the next step.")
        self.steps(frame, "Press Get the Web Clipper and add it to your browser.",
                   "When the clipper asks which vault to use, choose yours.",
                   "Press Save Oso's template. It saves a file to your Downloads folder.",
                   "Click the clipper's icon in your browser's toolbar, click the gear to open its settings, open Templates, "
                   "choose Import, and pick the file you just saved.")
        self.link(frame, "Get the Web Clipper", "https://obsidian.md/clipper")
        ttk.Button(frame, text="Save Oso's template", command=lambda: self.background("Downloading the template", save_template)).pack(
            anchor="w", pady=3)

    def page_obsidian_plugins(self, frame) -> None:
        self.why(frame, "Spaced Repetition shows the flashcards Oso makes, timed so you review each card just before you'd "
                        "forget it. Dataview lets the course page Oso makes show a live list of the course's notes.")
        self.steps(frame, "In Obsidian, click the gear at the bottom left to open Settings, then choose Community plugins.",
                   "Click Browse, search for Spaced Repetition, click Install, then Enable.",
                   "Go back, search for Dataview, click Install, then Enable.")

    # -- courses

    def page_first_course(self, frame) -> None:
        self.why(frame, "Oso sets up each course from its syllabus: every due date, exam, and grade weight, and your class "
                        "times on your calendar.")
        self.steps(frame, "Open the course syllabus in your browser and click the Web Clipper's icon to save it. (A syllabus "
                          "PDF dropped into your vault's Clippings folder works too.)",
                   "In a chat in the School project, type /create-course and the course name, for example "
                   "/create-course Intro to Engineering.",
                   "Claude shows every date, exam, grade weight, and class time it found. Check them, fix anything wrong, "
                   "and confirm. If the syllabus has no class times, Claude asks; your registration schedule has them.")
        self.text(frame, "One course is enough for now. Do the same for each of your other courses whenever you're ready.")

    # -- Google Cloud

    def page_g_project(self, frame) -> None:
        self.why(frame, "Oso can keep its own Google calendar (your classes, urgent changes like a moved exam, reminders), read "
                        "the Gmail account your school email is forwarded to, and keep your tasks in Google Tasks on your "
                        "phone. Google only lets a program into your calendar, email, or tasks once it's registered, so you "
                        "register your own private copy of Oso. It's free, takes about ten minutes over the next few pages, and "
                        "only you will ever use it. Without it, Oso still works; urgent changes just stay in your briefing.")
        self.steps(frame, "Press Open Google Cloud and sign in with your Google account. Accept the terms if it asks.",
                   "Click the project picker at the top of the page, next to the Google Cloud name, then New project.",
                   "Name the project Oso and click Create.",
                   "When it's made, open the project picker again and choose Oso, so it's the project you're working in.")
        self.link(frame, "Open Google Cloud", CLOUD)

    def page_g_apis(self, frame) -> None:
        self.why(frame, "Each Google service a program uses has to be switched on for its project: one for the calendar, one "
                        "for email, one for tasks.")
        self.steps(frame, "Press Google Calendar API. Check that Oso is the project shown at the top, then click Enable.",
                   "Press Gmail API and click Enable.",
                   "Press Google Tasks API and click Enable.")
        self.link(frame, "Google Calendar API", f"{CLOUD}/apis/library/calendar-json.googleapis.com")
        self.link(frame, "Gmail API", f"{CLOUD}/apis/library/gmail.googleapis.com")
        self.link(frame, "Google Tasks API", f"{CLOUD}/apis/library/tasks.googleapis.com")

    def page_g_app(self, frame) -> None:
        self.why(frame, "Google shows this name whenever it asks you to allow access, so you can tell it's Oso asking.")
        self.steps(frame, "Press Open Google Auth Platform and click Get started.",
                   "For App name type Oso, choose your email as the User support email, and click Next.",
                   "For Audience choose External, and click Next.",
                   "For Contact information type your email, and click Next.",
                   "Agree to the policy, click Continue, then Create.")
        self.link(frame, "Open Google Auth Platform", f"{CLOUD}/auth/overview")

    def page_g_publish(self, frame) -> None:
        self.why(frame, "Until the app is published, Google makes you connect again every seven days. Publishing doesn't make "
                        "it public: only someone with your client file (the next step) can use it, and that's only you.")
        self.steps(frame, "Press Open Audience.",
                   "Under Publishing status, click Publish app, then Confirm.")
        self.link(frame, "Open Audience", f"{CLOUD}/auth/audience")

    def page_g_client(self, frame) -> None:
        self.why(frame, "The client file is how Oso proves to Google that it's the app you registered. Keep it private, like a "
                        "password.")
        self.steps(frame, "Press Open Clients and click Create client.",
                   "For Application type choose Desktop app, name it Oso, and click Create.",
                   "In the box that appears, click Download JSON and save the file. Your Downloads folder is fine.")
        self.link(frame, "Open Clients", f"{CLOUD}/auth/clients")

    def page_g_connect(self, frame) -> None:
        self.why(frame, "Last, connect each one. Each time, a browser window opens for you to sign in. Google warns that the app "
                        "isn't verified: that's because it's your own private app, which Google never reviews. Click Advanced, "
                        "then Go to Oso, and allow access.")
        self.steps(frame, "Press Connect Google Calendar and choose the file you downloaded. Sign in and allow access.",
                   "Press Connect Google Tasks, sign in, and allow Oso to manage your tasks.",
                   "Email: Oso reads the Gmail account your school email is forwarded to. If your school email isn't "
                   "forwarded there yet, set up forwarding in your school email first. Then press Connect email, sign in "
                   "with that Gmail account, and allow Oso to read your email and send email (it sends only your feedback "
                   "about Oso, to the person who builds it).")
        from . import actions
        from .settings_gui import _connect_calendar, _email_client_file

        def calendar() -> None:
            path = filedialog.askopenfilename(parent=self.win, title="Choose the client file you downloaded from Google Cloud",
                                              filetypes=[("JSON", "*.json"), ("All files", "*")])
            if not path:
                self.say("No file chosen.")
                return
            cfg = self.cfg()
            self.background("Connecting Google Calendar (sign in in your browser)", lambda: _connect_calendar(cfg, Path(path)))

        def google(connect) -> None:
            client = _email_client_file()
            if client is False:
                self.say("No file chosen.")
                return
            self.background("Opening the Google sign-in in your browser", lambda: connect(client))

        ttk.Button(frame, text="Connect Google Calendar…", command=calendar).pack(anchor="w", pady=3)
        ttk.Button(frame, text="Connect Google Tasks…", command=lambda: google(actions.connect_tasks)).pack(anchor="w", pady=3)
        ttk.Button(frame, text="Connect email…", command=lambda: google(actions.connect_email)).pack(anchor="w", pady=3)

    # -- extras

    def page_groupme(self, frame) -> None:
        self.why(frame, "Only if your classes or clubs use GroupMe. Oso reads your groups for what affects your schedule, like "
                        "a moved study session or an event flyer, so you don't have to.")
        self.steps(frame, "Press Open dev.groupme.com and sign in with your GroupMe account.",
                   "Click Access Token at the top right and copy it.",
                   "Press Connect GroupMe and paste it.")
        self.link(frame, "Open dev.groupme.com", "https://dev.groupme.com")
        from .settings_gui import _connect_groupme

        ttk.Button(frame, text="Connect GroupMe…", command=lambda: self.say(_connect_groupme(self.win))).pack(anchor="w", pady=3)

    def page_briefing(self, frame) -> None:
        self.why(frame, "Each morning, a short rundown in the Claude app on your phone: what's due, what changed, your classes, "
                        "and what to focus on. It runs in Claude's cloud, so it comes even when this computer is off.")
        self.steps(frame, "In the Claude app, open Cowork and make a new scheduled task.",
                   "Set it to run every day at the time you usually wake up.",
                   "For the instruction, type: Run the oso-briefing skill.",
                   "Save it.")

    def page_chrome(self, frame) -> None:
        self.why(frame, "Only needed to save online textbook pages into a course's book with /scrape-page.")
        self.steps(frame, "Press Open the Chrome extension, add the Claude extension to Chrome, and sign in with your Claude "
                          "account.",
                   "The first time you save pages from a textbook site, allow Claude to read that site when the extension asks.")
        self.link(frame, "Open the Chrome extension", "https://claude.ai/chrome")

    def page_remarkable(self, frame) -> None:
        self.why(frame, "Only if you take notes on a reMarkable tablet. Photographed or scanned paper notes work just as well "
                        "without one.")
        self.steps(frame, "On the tablet, open Settings, then Storage, and turn on USB web interface.",
                   "Make a folder on the tablet for each course, named exactly like the course's folder in your vault "
                   "(for example Physics). Notebooks anywhere else on the tablet are never touched.",
                   "Plug the tablet into this computer with its cable. Oso copies the notebooks you changed on its next "
                   "check; leave it plugged in for a few minutes.")

    def finished_page(self) -> None:
        ttk.Label(self.page, text="You're set up", font=("TkDefaultFont", 14, "bold")).pack(anchor="w", pady=(0, 12))
        self.text(self.page, "Oso checks for changes every 15 minutes from now on. Anything you skipped is on the Status tab of the "
                             f"Oso window, which opens from {_app_name()}, or when you ask Claude to open your settings. Every "
                             "step is also written up in the install guide.")
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
