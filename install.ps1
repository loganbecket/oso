# Oso installer for Windows. Paste this into PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loganbecket/oso/master/install.ps1 | iex"

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

Write-Host "Installing the Oso service (this takes a minute or two)..."
uv tool install --force --python 3.12 "https://github.com/$Repo/archive/refs/heads/master.zip"
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
oso update
oso sync
oso doctor --fix

Write-Host ""
Write-Host "Oso is installed. Next:" -ForegroundColor Cyan
Write-Host "  1. Open Obsidian and open $Vault as a vault."
Write-Host "  2. In the Claude app, open Customize, then Plugins, choose Add marketplace, enter $Repo, and install Oso."
Write-Host "  3. Run 'oso settings' any time to change how often Oso checks, quiet hours, updates, and the rest."
