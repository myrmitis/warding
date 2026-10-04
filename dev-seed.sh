#!/bin/bash
# Copy the Junction data home into .junction-dev/ for local development.
# Safe to re-run — wipes .junction-dev first so you get a clean snapshot.
#
# Usage: ./dev-seed.sh
set -e

# Seed from the live data home: an explicit JUNCTION_HOME, else ~/.junction.
if [ -n "${JUNCTION_HOME:-}" ] && [ -d "$JUNCTION_HOME" ]; then
  SRC="$JUNCTION_HOME"
elif [ -d "$HOME/.junction" ]; then
  SRC="$HOME/.junction"
else
  SRC=""
fi
DST="$(cd "$(dirname "$0")" && pwd)/.junction-dev"

if [ -z "$SRC" ]; then
  echo "No Junction data home found — nothing to seed."
  exit 0
fi

if [ -d "$DST" ]; then
  # Refuse to rm -rf if .junction-dev is a symlink (could follow to unrelated dir)
  if [ -L "$DST" ]; then
    echo "ERROR: .junction-dev is a symlink — refusing to remove. Delete it manually."
    exit 1
  fi
  echo "Removing existing .junction-dev/ ..."
  rm -rf "$DST"
fi

echo "Copying $SRC → .junction-dev/ ..."
cp -R "$SRC" "$DST"

echo "Done. Start the gateway with:"
echo "  JUNCTION_HOME=.junction-dev bin/junction gateway"
