"""Register 'oso sync' as a systemd user timer on Linux (for the builder's machine and any Linux student)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_SERVICE = """[Unit]
Description=Oso: pull course sources and rewrite Today.md

[Service]
Type=oneshot
ExecStart={command} sync
"""

_TIMER = """[Unit]
Description=Run Oso sync every {minutes} minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec={minutes}min
Persistent=true

[Install]
WantedBy=timers.target
"""


def install_timer(every_minutes: int = 60) -> str:
    exe = shutil.which("oso") or sys.argv[0]
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "oso-sync.service").write_text(_SERVICE.format(command=exe), encoding="utf-8")
    (unit_dir / "oso-sync.timer").write_text(_TIMER.format(minutes=every_minutes), encoding="utf-8")
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True, text=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "oso-sync.timer"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        return f"Wrote the units to {unit_dir} but could not start the timer: {detail.strip()}"
    return f"Installed the oso-sync timer: runs every {every_minutes} minutes and catches up after sleep (Persistent=true)."
