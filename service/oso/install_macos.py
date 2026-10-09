"""Register 'oso sync' as a launchd user agent on macOS."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.oso.sync"

_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{command}</string><string>sync</string></array>
  <key>StartInterval</key><integer>{seconds}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


WATCH_LABEL = "com.oso.watch"

_WATCH_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{python}</string><string>-m</string><string>oso.watch</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def install_agent(every_minutes: int = 60) -> str:
    exe = shutil.which("oso") or sys.argv[0]
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    log = Path.home() / "Library" / "Logs" / "oso-sync.log"
    plist = agents / f"{LABEL}.plist"
    plist.write_text(_PLIST.format(label=LABEL, command=exe, seconds=every_minutes * 60, log=log), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    try:
        subprocess.run(["launchctl", "load", str(plist)], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        return f"Wrote {plist} but could not start it: {detail.strip()}"
    watch = agents / f"{WATCH_LABEL}.plist"
    watch.write_text(_WATCH_PLIST.format(label=WATCH_LABEL, python=sys.executable, log=log.with_name("oso-watch.log")), encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(watch)], capture_output=True)
    subprocess.run(["launchctl", "load", str(watch)], capture_output=True)
    from . import shortcut

    link_mcp()
    return (f"Installed the {LABEL} agent: runs every {every_minutes} minutes and on login. Missed runs are made up when the Mac wakes. "
            f"New files in your course folders are taken in as soon as they arrive. {shortcut.create() or 'Oso is in your Applications folder.'}")


LINK_DIRS = (Path("/usr/local/bin"), Path("/opt/homebrew/bin"))


def link_mcp() -> str:
    """Put `oso-mcp` where apps opened from the Dock can see it. Apps do not get the shell's PATH, so the Claude app
    cannot start Oso's tools from ~/.local/bin on its own."""
    target = shutil.which("oso-mcp") or str(Path.home() / ".local" / "bin" / "oso-mcp")
    if not Path(target).exists():
        return "The oso-mcp command is not installed; run the Oso installer again."
    for d in LINK_DIRS:
        link = d / "oso-mcp"
        try:
            if link.is_symlink() or link.exists():
                if link.resolve() == Path(target).resolve():
                    return f"The Claude app can find Oso through {link}."
                link.unlink()
            link.symlink_to(target)
            return f"Linked {link} so the Claude app can find Oso."
        except OSError:
            continue
    return ("Oso could not make a link in /usr/local/bin. In Terminal, run: sudo ln -sf "
            f"\"{target}\" /usr/local/bin/oso-mcp")


def mcp_reachable() -> bool:
    """Whether an app opened from the Dock would find oso-mcp."""
    gui_path = ""
    try:
        gui_path = subprocess.run(["launchctl", "getenv", "PATH"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    dirs = [Path(p) for p in gui_path.split(":") if p] or ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return any((Path(d) / "oso-mcp").exists() for d in [*dirs, *LINK_DIRS])


def installed() -> bool:
    return (Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist").exists()
