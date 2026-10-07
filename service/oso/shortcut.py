"""An "Oso" entry in the Start menu (Windows), Applications (macOS), or the app menu (Linux) that opens the
Oso window with no command window behind it. Made by the installer and again on every update, so it
always points at the Python Oso currently runs from.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# Opens the Oso window from anywhere on Windows (Windows honors a shortcut key on Start menu shortcuts).
HOTKEY = "Ctrl+Alt+O"


def _python() -> str:
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if sys.platform == "win32" and windowless.exists() else exe)


def location() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Oso.lnk"
    if sys.platform == "darwin":
        return Path.home() / "Applications" / "Oso.app"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications" / "oso.desktop"


def create() -> str | None:
    """Make or refresh the shortcut. None when it worked, otherwise a plain sentence."""
    path = location()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            return _windows(path)
        if sys.platform == "darwin":
            _macos(path)
        else:
            _linux(path)
    except OSError as e:
        return f"The Oso shortcut could not be made ({e.strerror or e})."
    return None


def _windows(path: Path) -> str | None:
    def q(text: str) -> str:  # inside a single-quoted PowerShell string
        return str(text).replace("'", "''")

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
        "$s.TargetPath = '{python}'; $s.Arguments = '-m oso settings'; "
        "$s.WorkingDirectory = '{home}'; $s.Description = 'Oso status and settings'; $s.Hotkey = '{hotkey}'; $s.Save()"
    ).format(lnk=q(path), python=q(_python()), home=q(Path.home()), hotkey=HOTKEY)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return "The Oso shortcut could not be added to the Start menu."
    return None


_INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Oso</string>
  <key>CFBundleIdentifier</key><string>com.oso.settings</string>
  <key>CFBundleExecutable</key><string>Oso</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict>
</plist>
"""


def _macos(app: Path) -> None:
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Info.plist").write_text(_INFO_PLIST, encoding="utf-8")
    launcher = macos / "Oso"
    launcher.write_text(f'#!/bin/sh\nexec "{_python()}" -m oso settings\n', encoding="utf-8")
    launcher.chmod(0o755)


def _linux(path: Path) -> None:
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=Oso\nComment=Oso status and settings\n"
        f'Exec="{_python()}" -m oso settings\nTerminal=false\nCategories=Education;\n',
        encoding="utf-8",
    )
