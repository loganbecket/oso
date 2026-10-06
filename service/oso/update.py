"""Install and update the service from GitHub's downloads, with no Git.

Two channels:
- stable: the newest version tag (v1.2.3) on the repository. Until one exists, stable falls back to latest.
- latest: whatever is on the master branch.

Stable is the default; switching to latest is done in the settings window (`channel` in the config).
`oso update` installs the newest version on the configured channel; `oso update --version v0.1.0` (or a
commit) installs that exact version, for rolling back.
Once a day the sync asks GitHub whether something newer exists and says so in Today.md and `oso doctor`.

Windows will not let a running program replace its own files, so there the reinstall is handed to a
PowerShell window (visible, closing itself when done) that stops every Oso process (including the one Claude keeps open) first.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

import requests

from . import config as cfgmod
from .config import Config
from .db import now_iso

API = "https://api.github.com/repos/{repo}"
ZIP_BRANCH = "https://github.com/{repo}/archive/refs/heads/master.zip"
ZIP_TAG = "https://github.com/{repo}/archive/refs/tags/{tag}.zip"
ZIP_COMMIT = "https://github.com/{repo}/archive/{sha}.zip"
CHANNELS = ("stable", "latest")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

META = "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);"


class UpdateError(Exception):
    pass


def _get(url: str, **kw):
    r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=20, **kw)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise UpdateError("GitHub is limiting requests right now; try again in an hour")
    r.raise_for_status()
    return r


def newest_tag(repo: str) -> str | None:
    """The highest version tag (v1.2.3), or None if the repository has none."""
    tags = [t["name"] for t in _get(API.format(repo=repo) + "/tags", params={"per_page": 100}).json()]
    versions = [(tuple(int(x) for x in m.groups()), t) for t in tags if (m := _SEMVER.match(t))]
    return max(versions)[1] if versions else None


def master_commit(repo: str) -> str:
    return _get(API.format(repo=repo) + "/commits/master").json()["sha"]


def target(cfg: Config) -> dict:
    """What the chosen channel points to right now: version label, download URL, and the note to show."""
    if cfg.channel == "stable":
        tag = newest_tag(cfg.repo)
        if tag:
            return {"version": tag, "url": ZIP_TAG.format(repo=cfg.repo, tag=tag), "fallback": False}
    sha = master_commit(cfg.repo)
    return {"version": sha[:12], "url": ZIP_BRANCH.format(repo=cfg.repo), "fallback": cfg.channel == "stable"}


def status(cfg: Config) -> dict:
    try:
        t = target(cfg)
    except (requests.RequestException, UpdateError, KeyError, ValueError) as e:
        return {"known": False, "available": False, "message": f"Could not check for Oso updates: {_plain(e)}"}
    installed = cfg.installed_version
    available = installed is not None and installed != t["version"]
    where = "the latest version" if cfg.channel == "latest" or t["fallback"] else f"version {t['version']}"
    msg = f"An Oso update is available ({where}). Run 'oso update'." if available else f"Oso is up to date ({cfg.channel})."
    if t["fallback"]:
        msg += " No stable release has been tagged yet, so stable follows the latest version for now."
    return {"known": True, "available": available, "installed": installed, "target": t["version"], "message": msg}


def check_daily(conn: sqlite3.Connection, cfg: Config, now: datetime) -> str | None:
    """Ask GitHub at most once a day; return the message to show in Today.md, or None."""
    conn.executescript(META)
    row = conn.execute("SELECT value FROM meta WHERE key = 'update_checked_at'").fetchone()
    last = datetime.fromisoformat(row["value"]) if row else None
    if last is not None and now.astimezone(last.tzinfo) - last < timedelta(hours=24):
        cached = conn.execute("SELECT value FROM meta WHERE key = 'update_message'").fetchone()
        return cached["value"] if cached and cached["value"] else None
    st = status(cfg)
    message = st["message"] if st["available"] else ""
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_checked_at', ?)", (now_iso(),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('update_message', ?)", (message,))
    return message or None


def run(cfg: Config, channel: str | None = None, version: str | None = None) -> str:
    """Install the newest version on the channel, or an exact version or commit. Returns a report."""
    if channel:
        if channel not in CHANNELS:
            return f"Channel must be one of: {', '.join(CHANNELS)}."
        cfg.channel = channel
    try:
        if version:
            if _SEMVER.match(version):
                t = {"version": version, "url": ZIP_TAG.format(repo=cfg.repo, tag=version), "fallback": False}
            else:
                t = {"version": version[:12], "url": ZIP_COMMIT.format(repo=cfg.repo, sha=version), "fallback": False}
        else:
            t = target(cfg)
    except (requests.RequestException, UpdateError, KeyError, ValueError) as e:
        return f"Could not reach GitHub: {_plain(e)}"
    lines = []
    if not version and cfg.installed_version == t["version"]:
        cfgmod.save(cfg)
        return f"Oso is already at {t['version']} on the {cfg.channel} channel."
    try:
        done = install(t["url"])
    except UpdateError as e:
        return f"Could not install Oso {t['version']}: {e}"
    cfg.installed_version = t["version"]
    cfgmod.save(cfg)
    label = f"{t['version']} ({'pinned' if version else cfg.channel})"
    if done:
        lines.append(f"Installed Oso {label}.")
    else:
        lines.append(f"Oso {label} is installing in a new window, which closes by itself when it's done. "
                     "Then restart the Claude app so it reconnects.")
    if t["fallback"]:
        lines.append("No stable release has been tagged yet, so this is the latest version.")
    if done:
        lines.append(_reschedule(cfg))
    return "\n".join(lines)


def record(cfg: Config, version: str) -> str:
    """Note which version the installer just put in place, without reinstalling."""
    cfg.installed_version = version
    cfgmod.save(cfg)
    return f"Recorded Oso {version} as installed."


def install(url: str) -> bool:
    """Reinstall from url. True when done now; False when handed to the update window (Windows)."""
    uv = shutil.which("uv")
    if not uv:
        raise UpdateError("uv is not installed; run the Oso installer again")
    if sys.platform == "win32":
        _install_in_window(uv, url)
        return False
    r = subprocess.run([uv, "tool", "install", "--force", "--python", "3.12", url], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise UpdateError((r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout) else "uv failed")
    return True


# Waits up to a minute for the process that asked for the update to exit, stops every Oso process
# (oso.exe, oso-mcp.exe, and the Python they run from the uv tool folder), then reinstalls, retrying
# while Windows still holds a file.
_WIN_SCRIPT = """$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'Updating Oso'
$log = '{log}'
$uv = '{uv}'
$url = '{url}'
"Update started $(Get-Date -Format s)" | Out-File -Encoding utf8 $log
Write-Host 'Updating Oso. This window closes by itself when the update is done.' -ForegroundColor Cyan
Wait-Process -Id {pid} -Timeout 60 -ErrorAction SilentlyContinue
for ($i = 1; $i -le 3; $i++) {{
    Write-Host 'Stopping any running copy of Oso...'
    Get-CimInstance Win32_Process | Where-Object {{
        $_.ProcessId -ne $PID -and ($_.Name -in @('oso.exe', 'oso-mcp.exe') -or $_.CommandLine -match '\\\\tools\\\\oso\\\\')
    }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
    Start-Sleep -Seconds 2
    Write-Host 'Installing...'
    cmd /c "`"$uv`" tool install --force --python 3.12 `"$url`" 2>&1" | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -eq 0) {{
        'Update finished' | Out-File -Append -Encoding utf8 $log
        Write-Host 'Oso is updated. Restart the Claude app so it reconnects.' -ForegroundColor Green
        Start-Sleep -Seconds 3
        exit 0
    }}
    Write-Host 'Windows is still holding a file; trying again...' -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}}
'Update failed; run the Oso installer again' | Out-File -Append -Encoding utf8 $log
Write-Host 'The update did not finish. Run the Oso installer lines again (step 2.2 in the guide); your settings are kept.' -ForegroundColor Red
Read-Host 'Press Enter to close'
exit 1
"""


def _install_in_window(uv: str, url: str) -> None:
    def q(text: str) -> str:  # inside a single-quoted PowerShell string
        return str(text).replace("'", "''")

    script = cfgmod.data_dir() / "update.ps1"
    log = cfgmod.data_dir() / "update.log"
    script.write_text(_WIN_SCRIPT.format(log=q(log), pid=os.getpid(), uv=q(uv), url=q(url)), encoding="utf-8")
    # Created through WMI so the job outlives this process: the oso.exe launcher kills its children on exit.
    # ShowWindow 1 makes the window visible, so the student can watch the installer.
    command = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}"'
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$su = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]1}; "
         f"(Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{q(command)}'; ProcessStartupInformation=$su}}).ReturnValue"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0 or r.stdout.strip() != "0":
        raise UpdateError("Windows would not open the update window; run the Oso installer again")


def _reschedule(cfg: Config) -> str:
    if sys.platform == "win32":
        from .install_windows import install_task

        return install_task(every_minutes=cfg.sync_interval_minutes)
    if sys.platform == "darwin":
        from .install_macos import install_agent

        return install_agent(every_minutes=cfg.sync_interval_minutes)
    from .install_linux import install_timer

    return install_timer(every_minutes=cfg.sync_interval_minutes)


def _plain(e: Exception) -> str:
    text = str(e) or type(e).__name__
    return text.strip().splitlines()[-1][:160]
