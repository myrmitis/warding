#!/bin/bash
# Junction persistent-session setup.
#
# Installs junction up as a systemd user service.
# Requires the systemd user manager to be running (see README.md Phase 1).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME=$(whoami)
HOSTNAME=$(hostname)

echo "Junction persistent-session setup"
echo ""

# ── Check: systemd user manager running? ──
if ! systemctl --user status >/dev/null 2>&1; then
    echo "❌ Systemd user manager is not running."
    echo "   Complete Phase 1 in README.md first (requires sudo, one-time)."
    exit 1
fi
echo "✅ Systemd user manager running"

# ── Check: junction already running in tmux? ──
if pgrep -f "junction up\|junction up\|junction gateway\|junction gateway" | grep -v $$ >/dev/null 2>&1; then
    echo ""
    echo "⚠️  Junction is already running (tmux or manual)."
    echo "   Kill it first: tmux kill-session -t junction"
    echo "   Then re-run this script."
    exit 1
fi

# ── Install user service ──
echo "→ Installing junction user service..."
USER_UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR"
NODE_VERSION=$(node --version 2>/dev/null || basename "$(ls -d "$HOME"/.nvm/versions/node/v* 2>/dev/null | tail -1)")

# Resolve the junction binary on PATH
JUNCTION_BIN="$(command -v junction 2>/dev/null)" \
  || { echo "❌ junction not found in PATH"; exit 1; }
echo "  Binary: $JUNCTION_BIN"

sed -e "s/%u/$USERNAME/g" \
    -e "s|JUNCTION_BIN|$JUNCTION_BIN|g" \
    -e "s/NVM_NODE_VERSION/$NODE_VERSION/g" \
    "$SCRIPT_DIR/junction.service" > "$USER_UNIT_DIR/junction.service"

systemctl --user daemon-reload
systemctl --user enable junction
systemctl --user start junction

echo ""
systemctl --user status junction --no-pager || true

# ── Mac instructions ──
echo ""
echo "━━━ Mac Setup (run on your laptop) ━━━"
echo ""
echo "scp $USERNAME@$HOSTNAME:$SCRIPT_DIR/com.junction.tunnel.plist ~/Library/LaunchAgents/"
echo "sed -i '' 's|USER@REMOTE_HOST|$USERNAME@$HOSTNAME|g' ~/Library/LaunchAgents/com.junction.tunnel.plist"
echo "launchctl load ~/Library/LaunchAgents/com.junction.tunnel.plist"
echo ""
echo "Done! Dashboard: http://localhost:5476"
