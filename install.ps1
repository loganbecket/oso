# Oso installer for Windows. Run in PowerShell from the folder you cloned this repo into:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Vault "C:\Users\you\Google Drive\My Drive\Vault"

param(
    [Parameter(Mandatory = $true)][string]$Vault,
    [string]$Timezone = "America/New_York"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python package manager)..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Installing the Oso service..."
uv tool install --force --python 3.12 $repo

if (-not (Test-Path $Vault)) {
    Write-Host "Creating the vault folder at $Vault"
    New-Item -ItemType Directory -Path $Vault | Out-Null
}
Copy-Item -Path (Join-Path $repo "vault-template\*") -Destination $Vault -Recurse -Force

Write-Host ""
Write-Host "In Canvas, open Calendar, click 'Calendar Feed', and copy the address."
$feed = Read-Host "Paste the Canvas Calendar Feed URL (or press Enter to skip)"
if ($feed) {
    oso init --vault $Vault --timezone $Timezone --canvas-feed-url $feed
} else {
    oso init --vault $Vault --timezone $Timezone --canvas-feed-url ""
}

oso install-task
oso sync
oso doctor --fix

Write-Host ""
Write-Host "Oso is installed. Next:"
Write-Host "  1. Open Obsidian and open $Vault as a vault."
Write-Host "  2. In Claude Code or Cowork, install the plugin from $repo\plugin and ask it to set up your first course."
Write-Host "  3. Run oso settings any time to change how often Oso checks, quiet hours, and the rest."
