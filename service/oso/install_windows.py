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
    <Exec><Command>{command}</Command><Arguments>-m oso sync</Arguments></Exec>
  </Actions>
</Task>
"""


WATCH_TASK = "Oso Watch"

_WATCH_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Oso: take in new course files as soon as they arrive</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Priority>7</Priority>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{command}</Command><Arguments>-m oso.watch</Arguments></Exec>
  </Actions>
</Task>
"""


def watcher_command() -> str:
    """Python without a console window, from Oso's own environment."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else exe)


def _create(name: str, xml: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml)
        xml_path = Path(f.name)
    try:
        subprocess.run(["schtasks", "/Create", "/TN", name, "/XML", str(xml_path), "/F"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return e.stderr.strip() or e.stdout.strip()
    finally:
        xml_path.unlink(missing_ok=True)
    return None


def install_task(every_minutes: int = 60) -> str:
    if sys.platform != "win32":
        return "Scheduled task installation only applies on Windows. On this machine, run 'oso sync' from cron or a timer."
    exe = watcher_command()  # windowless Python, so the check never opens a command window
    # Naming the user keeps the logon trigger to this account; without it Windows demands an administrator.
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    error = _create(TASK_NAME, _XML.format(minutes=every_minutes, command=escape(exe), user=escape(user)))
    if error:
        return f"Could not create the scheduled task: {error}"
    watch_error = _create(WATCH_TASK, _WATCH_XML.format(command=escape(watcher_command()), user=escape(user)))
    if watch_error is None:
        subprocess.run(["schtasks", "/Run", "/TN", WATCH_TASK], capture_output=True, text=True)  # start it now, not at next sign-in
    note = "" if watch_error is None else f" The folder watcher could not be set up ({watch_error}); new files wait for the next check."
    from . import shortcut

    note += f" {shortcut.create() or 'Oso is in the Start menu; pin it to the taskbar if you like.'}"
    return (f"Installed '{TASK_NAME}': runs every {every_minutes} minutes, wakes the laptop to run, and catches up after sleep. "
            f"New files in your course folders are taken in as soon as they arrive.{note}")
