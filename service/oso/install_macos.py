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
    return f"Installed the {LABEL} agent: runs every {every_minutes} minutes and on login. Missed runs are made up when the Mac wakes."


def installed() -> bool:
    return (Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist").exists()
