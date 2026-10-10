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
Write-Host "The Set up Oso window is opening. Leave this window open until you close that one."
oso setup
$Vault = oso setup --show-vault
if (-not $Vault) {
    Write-Host ""
    Write-Host "Setup closed before a vault was chosen. Run this installer again to finish." -ForegroundColor Yellow
    exit 1
}

if ($Version) { oso update --installed $Version | Out-Null }
oso sync
oso install-task
oso doctor --fix

Write-Host ""
Write-Host "Oso is installed. Open Oso from the Start menu (or press Ctrl+Alt+O) any time; anything you skipped in setup" -ForegroundColor Cyan
Write-Host "is on its Status tab." -ForegroundColor Cyan
