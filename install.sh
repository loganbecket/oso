#!/usr/bin/env bash
# Oso installer for macOS and Linux. Paste this into a terminal:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/loganbecket/oso/master/install.sh)"
set -euo pipefail

REPO="${OSO_REPO:-loganbecket/oso}"

echo
echo "Oso installer"
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv, the tool that installs Oso..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "Installing the Oso service (this takes a minute or two)..."
uv tool install --force --python 3.12 "https://github.com/$REPO/archive/refs/heads/master.zip"
uv tool update-shell >/dev/null 2>&1 || true

echo
echo "Where is your vault? This is the folder you created in Obsidian (inside your Google Drive folder on macOS)."
read -r -p "Vault folder: " VAULT
VAULT="${VAULT/#\~/$HOME}"
VAULT="${VAULT%\"}"; VAULT="${VAULT#\"}"
mkdir -p "$VAULT"

read -r -p "Time zone (press Enter for America/New_York, or type e.g. America/Chicago): " TZ_NAME
TZ_NAME="${TZ_NAME:-America/New_York}"

echo
echo "In Canvas, open Calendar, click 'Calendar Feed', and copy the address."
read -r -p "Paste the Canvas Calendar Feed URL (or press Enter to skip): " FEED

oso init --vault "$VAULT" --timezone "$TZ_NAME" --canvas-feed-url "${FEED:-}"
oso update

if [ "$(uname -s)" = "Linux" ] && command -v rclone >/dev/null 2>&1; then
  read -r -p "Keep the vault in sync with Google Drive through rclone (remote 'gdrive', folder 'Vault')? [y/N] " RC
  if [ "${RC:-n}" = "y" ] || [ "${RC:-n}" = "Y" ]; then
    rclone bisync "$VAULT" gdrive:Vault --resync || true
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_DIR/oso-drive.service" <<EOF2
[Unit]
Description=Oso: sync the vault with Google Drive

[Service]
Type=oneshot
ExecStart=$(command -v rclone) bisync "$VAULT" gdrive:Vault
EOF2
    cat > "$UNIT_DIR/oso-drive.timer" <<EOF2
[Unit]
Description=Sync the Oso vault with Google Drive every 15 minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF2
    systemctl --user daemon-reload && systemctl --user enable --now oso-drive.timer
  fi
fi

oso sync
oso doctor --fix || true

echo
echo "Oso is installed. Next:"
echo "  0. Close this terminal and open a new one. The 'oso' command only works in terminals opened after installing."
echo "  1. Open Obsidian and open $VAULT as a vault."
echo "  2. In the Claude app (or claude.ai), open Customize, then Plugins, choose Add marketplace, enter $REPO, and install Oso."
echo "  3. Run 'oso settings' any time to change how often Oso checks, quiet hours, updates, and the rest."
