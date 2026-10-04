#!/usr/bin/env bash
# Cloud Agent bootstrap for Junction.
#
# Idempotent: safe to re-run. It refreshes the frontend bundle, the backend
# virtualenv, and the agent config from the checked-out source.
set -euo pipefail

cd "$(dirname "$0")/.."

# The base image ships Python 3.12, but Ubuntu splits the stdlib venv /
# ensurepip module into a separate python3-venv package, which `make build`
# needs to create the backend virtualenv. Install it only when missing.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3-venv
fi

# Canonical build from CONTRIBUTING.md: build the Vite frontend, stage it into
# src/junction/static/dist, then editable-install the backend (with dev tools)
# into .venv. ensure-node.sh / ensure-python.sh are no-ops here because the base
# image already satisfies the Node >= 22.12 and Python >= 3.10 floors.
make build

# Install the agent config so the gateway and CLI resolve it on startup.
JUNCTION_PROJECT_DIR="$PWD" .venv/bin/junction setup --agent-only
