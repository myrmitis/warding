#!/bin/bash
# Copy the Warding data home into .warding-dev/ for local development.
# Safe to re-run — wipes .warding-dev first so you get a clean snapshot.
#
# Usage: ./dev-seed.sh
set -e

# Seed from the live data home: an explicit WARDING_HOME, else ~/.warding.
if [ -n "${WARDING_HOME:-}" ] && [ -d "$WARDING_HOME" ]; then
  SRC="$WARDING_HOME"
elif [ -d "$HOME/.warding" ]; then
  SRC="$HOME/.warding"
else
  SRC=""
fi
DST="$(cd "$(dirname "$0")" && pwd)/.warding-dev"

if [ -z "$SRC" ]; then
  echo "No Warding data home found — nothing to seed."
  exit 0
fi

if [ -d "$DST" ]; then
  # Refuse to rm -rf if .warding-dev is a symlink (could follow to unrelated dir)
  if [ -L "$DST" ]; then
    echo "ERROR: .warding-dev is a symlink — refusing to remove. Delete it manually."
    exit 1
  fi
  echo "Removing existing .warding-dev/ ..."
  rm -rf "$DST"
fi

echo "Copying $SRC → .warding-dev/ ..."
cp -R "$SRC" "$DST"

echo "Done. Start the gateway with:"
echo "  WARDING_HOME=.warding-dev bin/warding gateway"
