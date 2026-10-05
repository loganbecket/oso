#!/usr/bin/env bash
# Oso installer for Linux and macOS. Run from the folder you cloned this repo into:
#   ./install.sh "/path/to/your/vault" [timezone]
set -euo pipefail

VAULT="${1:?usage: ./install.sh /path/to/vault [timezone]}"
TZ_NAME="${2:-America/New_York}"
REPO="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing the Oso service..."
uv tool install --force --python 3.12 "$REPO"

mkdir -p "$VAULT"
cp -R "$REPO/vault-template/." "$VAULT/"

echo
echo "In Canvas, open Calendar, click 'Calendar Feed', and copy the address."
read -r -p "Paste the Canvas Calendar Feed URL (or press Enter to skip): " FEED
oso init --vault "$VAULT" --timezone "$TZ_NAME" --canvas-feed-url "${FEED:-}"

oso install-task
oso sync
oso doctor --fix || true

echo
echo "Oso is installed. Next:"
echo "  1. Open Obsidian and open $VAULT as a vault."
echo "  2. In Claude Code or Cowork, install the plugin from $REPO/plugin and ask it to set up your first course."
