"""Oso service: connectors, deadline database, and vault writer.

Nothing in this package calls a model. Intelligence lives in the Claude plugin.
"""

try:  # the version actually installed, from the package itself, so it can never go stale
    from importlib.metadata import PackageNotFoundError, version as _version

    __version__ = _version("oso")
except Exception:  # noqa: BLE001 - running from a source folder that was never installed
    __version__ = "unknown"

import subprocess as _subprocess
import sys as _sys

if _sys.platform == "win32":
    # Oso runs in the background (the scheduled check, the folder watcher), so nothing it starts may open a
    # window: not Claude Code reading a page, not LibreOffice, not PowerShell for a notification. Every
    # child process gets "no window" unless the caller asked for something specific (the visible update
    # window is created another way, through WMI).
    _Popen_init = _subprocess.Popen.__init__

    def _no_window_init(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = _subprocess.CREATE_NO_WINDOW
        _Popen_init(self, *args, **kwargs)

    _subprocess.Popen.__init__ = _no_window_init
