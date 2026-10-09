# Oso installer for Windows. Paste these into PowerShell, one line at a time:
#   irm https://raw.githubusercontent.com/loganbecket/oso/master/install.ps1 -OutFile $env:TEMP\oso-install.ps1
#   powershell -ExecutionPolicy Bypass -File $env:TEMP\oso-install.ps1

$ErrorActionPreference = "Stop"
$Repo = if ($env:OSO_REPO) { $env:OSO_REPO } else { "loganbecket/oso" }

Write-Host ""
Write-Host "Oso installer" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv, the tool that installs Oso..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# The newest version tag (stable), or master when there is none.
$Target = "https://github.com/$Repo/archive/refs/heads/master.zip"
$Version = $null
try {
    $Tag = (Invoke-RestMethod "https://api.github.com/repos/$Repo/tags?per_page=100").name |
        Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } |
        Sort-Object { [version]$_.TrimStart('v') } | Select-Object -Last 1
    if ($Tag) {
        $Target = "https://github.com/$Repo/archive/refs/tags/$Tag.zip"
        $Version = $Tag
    } else {
        $Version = (Invoke-RestMethod "https://api.github.com/repos/$Repo/commits/master").sha.Substring(0, 12)
    }
} catch { }

# Windows cannot replace files a running program holds, so stop any Oso already running
# (including the one the Claude app keeps open) before reinstalling.
$ToolDir = $null
try { $ToolDir = Join-Path (uv tool dir) 'oso' } catch { }
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('oso.exe', 'oso-mcp.exe') -or ($ToolDir -and $_.CommandLine -like "*$ToolDir*")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host "Installing the Oso service (this takes a minute or two)..."
uv tool install --force --python 3.12 $Target
uv tool update-shell | Out-Null
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

Write-Host ""
Write-Host "Where is your vault? This is the folder you created in Obsidian, inside your Google Drive folder,"
Write-Host "for example C:\Users\$env:USERNAME\My Drive\Vault"
$Vault = Read-Host "Vault folder"
$Vault = $Vault.Trim('"').Trim()
if (-not (Test-Path $Vault)) {
    New-Item -ItemType Directory -Path $Vault | Out-Null
}

$Timezone = Read-Host "Time zone (press Enter for America/New_York, or type e.g. America/Chicago)"
if (-not $Timezone) { $Timezone = "America/New_York" }

Write-Host ""
Write-Host "In Canvas, open Calendar, click 'Calendar Feed', and copy the address."
$Feed = Read-Host "Paste the Canvas Calendar Feed URL (or press Enter to skip)"

oso init --vault "$Vault" --timezone $Timezone --canvas-feed-url "$Feed"
if ($Version) { oso update --installed $Version | Out-Null }
oso sync
oso install-task
oso doctor --fix

Write-Host ""
Write-Host "Oso is installed. Next:" -ForegroundColor Cyan
Write-Host "  0. Close this PowerShell window and open a new one. The 'oso' command only works in windows opened after installing." -ForegroundColor Yellow
Write-Host "  1. Open Obsidian and open $Vault as a vault."
Write-Host "  2. In the Claude app, open Customize, then Plugins, choose Add marketplace, enter $Repo, and install Oso."
Write-Host "  3. If the Claude app was open, quit and reopen it so it reconnects to Oso."
Write-Host "  4. Run 'oso settings' any time to change how often Oso checks, quiet hours, updates, and the rest."
