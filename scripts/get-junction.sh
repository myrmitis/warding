#!/bin/sh
# Install Warding from this repository.
#
# Clones (or fast-forwards) a checkout, then runs minimal_install.sh.
# Does not start the server.
#
#   curl -fsSL https://raw.githubusercontent.com/laqaer/junction/main/scripts/get-junction.sh | sh
#
# Read this file before you run it. JUNCTION_SRC overrides the checkout.
# JUNCTION_BIN_DIR overrides where the warding link is written.
# --dry-run prints the plan and writes nothing.

set -eu

REPO="${JUNCTION_REPO:-https://github.com/laqaer/junction.git}"
DEST="${JUNCTION_SRC:-$HOME/.local/share/junction}"
BIN_DIR="${JUNCTION_BIN_DIR:-$HOME/.local/bin}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.10+)." >&2
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "python3 3.10+ is required." >&2
  exit 1
fi

if [ "${1:-}" = "--dry-run" ]; then
  echo "repo=$REPO"
  echo "dest=$DEST"
  echo "bin=$BIN_DIR"
  echo "installer=minimal_install.sh"
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    echo "dashboard=build"
  else
    echo "dashboard=missing-node"
  fi
  echo "next: warding setup && warding up"
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 22+ and npm are required so the dashboard can be built." >&2
  exit 1
fi

if [ -d "$DEST/.git" ]; then
  remote=$(git -C "$DEST" remote get-url origin)
  # Current slug, plus the previous GitHub location. A transfer leaves the
  # old URL as a redirect; refusing it would block an upgrade.
  case "$remote" in
    *myrmitis/junction*|*laqaer/junction*) ;;
    *)
      echo "refusing: $DEST is not a checkout of $REPO" >&2
      exit 1
      ;;
  esac
  if [ -n "$(git -C "$DEST" status --porcelain)" ]; then
    echo "refusing: $DEST has local changes" >&2
    exit 1
  fi
  git -C "$DEST" fetch --depth 1 origin
  git -C "$DEST" merge --ff-only FETCH_HEAD
elif [ -e "$DEST" ]; then
  echo "refusing: $DEST already exists" >&2
  exit 1
else
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 "$REPO" "$DEST"
fi

export JUNCTION_BIN_DIR="$BIN_DIR"
bash "$DEST/minimal_install.sh"
