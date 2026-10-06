"""Register 'oso sync' as a Windows scheduled task that wakes the laptop and catches up after sleep."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "Oso Sync"

_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Oso: pull course sources and rewrite Today.md</Description></RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition><Interval>PT{minutes}M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T06:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
    <LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{command}</Command><Arguments>sync</Arguments></Exec>
  </Actions>
</Task>
"""


def install_task(every_minutes: int = 60) -> str:
    if sys.platform != "win32":
        return "Scheduled task installation only applies on Windows. On this machine, run 'oso sync' from cron or a timer."
    exe = shutil.which("oso") or sys.argv[0]
    # Naming the user keeps the logon trigger to this account; without it Windows demands an administrator.
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    xml = _XML.format(minutes=every_minutes, command=escape(exe), user=escape(user))
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml)
        xml_path = Path(f.name)
    try:
        subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return f"Could not create the scheduled task: {e.stderr.strip() or e.stdout.strip()}"
    finally:
        xml_path.unlink(missing_ok=True)
    return f"Installed '{TASK_NAME}': runs every {every_minutes} minutes, wakes the laptop to run, and catches up after sleep."
