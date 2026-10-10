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

# The newest version tag (stable), or master when there is none.
TARGET="https://github.com/$REPO/archive/refs/heads/master.zip"
TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/tags?per_page=100" 2>/dev/null | grep -o '"name": *"v[0-9]*\.[0-9]*\.[0-9]*"' | sed 's/.*"v\([^"]*\)"/\1/' | sort -t. -k1,1n -k2,2n -k3,3n | tail -1 | sed 's/^/v/' || true)
if [ -n "${TAG:-}" ]; then
  TARGET="https://github.com/$REPO/archive/refs/tags/$TAG.zip"
fi

echo "Installing the Oso service${TAG:+ $TAG} (this takes a minute or two)..."
uv tool install --force --python 3.12 "$TARGET"
uv tool update-shell >/dev/null 2>&1 || true

echo
echo "The Set up Oso window is opening. Leave this window open until you close that one."
oso setup
VAULT=$(oso setup --show-vault || true)
if [ -z "$VAULT" ]; then
  echo
  echo "Setup closed before a vault was chosen. Run this installer again to finish."
  exit 1
fi

if [ -n "${TAG:-}" ]; then oso update --installed "$TAG"; else oso update; fi

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
oso install-task
oso doctor --fix || true

echo
echo "Oso is installed. Open Oso from Applications (macOS) or the app menu (Linux) any time; anything you skipped"
echo "in setup is on its Status tab."
