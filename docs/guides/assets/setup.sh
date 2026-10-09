#!/bin/bash
# Warding persistent-session setup.
#
# Installs warding up as a systemd user service.
# Requires the systemd user manager to be running (see README.md Phase 1).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USERNAME=$(whoami)
HOSTNAME=$(hostname)

echo "Warding persistent-session setup"
echo ""

# ── Check: systemd user manager running? ──
if ! systemctl --user status >/dev/null 2>&1; then
    echo "❌ Systemd user manager is not running."
    echo "   Complete Phase 1 in README.md first (requires sudo, one-time)."
    exit 1
fi
echo "✅ Systemd user manager running"

# ── Check: warding already running in tmux? ──
if pgrep -f "warding up\|warding up\|warding gateway\|warding gateway" | grep -v $$ >/dev/null 2>&1; then
    echo ""
    echo "⚠️  Warding is already running (tmux or manual)."
    echo "   Kill it first: tmux kill-session -t warding"
    echo "   Then re-run this script."
    exit 1
fi

# ── Install user service ──
echo "→ Installing warding user service..."
USER_UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR"
NODE_VERSION=$(node --version 2>/dev/null || basename "$(ls -d "$HOME"/.nvm/versions/node/v* 2>/dev/null | tail -1)")

# Resolve the warding binary on PATH
WARDING_BIN="$(command -v warding 2>/dev/null)" \
  || { echo "❌ warding not found in PATH"; exit 1; }
echo "  Binary: $WARDING_BIN"

sed -e "s/%u/$USERNAME/g" \
    -e "s|WARDING_BIN|$WARDING_BIN|g" \
    -e "s/NVM_NODE_VERSION/$NODE_VERSION/g" \
    "$SCRIPT_DIR/warding.service" > "$USER_UNIT_DIR/warding.service"

systemctl --user daemon-reload
systemctl --user enable warding
systemctl --user start warding

echo ""
systemctl --user status warding --no-pager || true

# ── Mac instructions ──
echo ""
echo "━━━ Mac Setup (run on your laptop) ━━━"
echo ""
echo "scp $USERNAME@$HOSTNAME:$SCRIPT_DIR/com.warding.tunnel.plist ~/Library/LaunchAgents/"
echo "sed -i '' 's|USER@REMOTE_HOST|$USERNAME@$HOSTNAME|g' ~/Library/LaunchAgents/com.warding.tunnel.plist"
echo "launchctl load ~/Library/LaunchAgents/com.warding.tunnel.plist"
echo ""
echo "Done! Dashboard: http://localhost:5476"
