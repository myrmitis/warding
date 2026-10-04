#!/usr/bin/env bash
# Developer ID sign a Junction .app bundle in place, inside-out, with the
# hardened runtime and a secure timestamp: everything Apple notarization
# requires of the code itself.
#
# Usage:
#   bash packaging/signing/sign.sh <app-path>
#
# Example:
#   SIGNING_IDENTITY="Developer ID Application: Example Corp (ABCDE12345)" \
#     bash packaging/signing/sign.sh "work/unsigned-app/Junction Nightly.app"
#
# Environment:
#   SIGNING_IDENTITY  (required) the codesign identity: its SHA-1 hash or its
#                     full "Developer ID Application: <Name> (<TEAMID>)" name
#   SIGNING_KEYCHAIN  (optional) the keychain holding that identity. Pinning it
#                     stops codesign from resolving a same-named identity in
#                     some other keychain on the search list.
#
# signing-plan.py derives the order from the bundle itself -- every nested
# Mach-O, then every nested code bundle, deepest first -- and the app is signed
# last, because codesign seals a bundle over the signatures of the code inside
# it. Executables and app bundles get Entitlements.entitlements; loadable code
# (dylibs, Python extensions, frameworks) gets none.
#
# Exit codes:
#   0 -- success, the bundle at <app-path> is signed and verified
#   1 -- usage error, missing environment, or not running on macOS
#   2 -- the signing plan could not be derived
#   4 -- codesign failed
#   6 -- verification failed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTITLEMENTS="$SCRIPT_DIR/Entitlements.entitlements"

# A timestamp-server blip fails a single codesign call; the bundle holds
# hundreds of nested objects, so one transient failure must not sink the run.
CODESIGN_ATTEMPTS=3
CODESIGN_RETRY_DELAY_SECONDS=5

APP_PATH="${1:-}"
if [ -z "$APP_PATH" ]; then
  echo "Usage: $0 <app-path>" >&2
  exit 1
fi
if [ ! -d "$APP_PATH" ]; then
  echo "ERROR: .app not found at $APP_PATH" >&2
  exit 1
fi
if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: codesign is macOS-only; run this on a macOS host" >&2
  exit 1
fi
: "${SIGNING_IDENTITY:?Set SIGNING_IDENTITY}"

log() { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }

CODESIGN_ARGS=(--force --options runtime --timestamp --sign "$SIGNING_IDENTITY")
if [ -n "${SIGNING_KEYCHAIN:-}" ]; then
  CODESIGN_ARGS+=(--keychain "$SIGNING_KEYCHAIN")
fi

# codesign_one <path> [extra codesign args...]
# Output is kept quiet on success (it is one "replacing existing signature"
# line per object) and printed in full on the final failed attempt.
codesign_one() {
  local target="$1"
  shift
  local attempt out
  for attempt in $(seq 1 "$CODESIGN_ATTEMPTS"); do
    if out=$(codesign "${CODESIGN_ARGS[@]}" "$@" "$target" 2>&1); then
      return 0
    fi
    if [ "$attempt" -lt "$CODESIGN_ATTEMPTS" ]; then
      echo "  codesign attempt ${attempt}/${CODESIGN_ATTEMPTS} failed for ${target}; retrying" >&2
      sleep "$CODESIGN_RETRY_DELAY_SECONDS"
    fi
  done
  echo "$out" >&2
  return 1
}

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
PLAN="$WORK_DIR/plan.tsv"

# ── 1. Plan ─────────────────────────────────────────────────────────────────
log "Planning the signing order for $(basename "$APP_PATH")..."
python3 "$SCRIPT_DIR/signing-plan.py" "$APP_PATH" > "$PLAN" || {
  echo "ERROR: could not derive the signing plan" >&2
  exit 2
}

# ── 2. Nested code, inside-out ──────────────────────────────────────────────
SIGNED=0
while IFS=$'\t' read -r KIND REL; do
  [ -n "$REL" ] || continue
  case "$KIND" in
    exec|app) EXTRA=(--entitlements "$ENTITLEMENTS") ;;
    code|bundle) EXTRA=() ;;
    *)
      echo "ERROR: unknown signing-plan entry kind '$KIND' for $REL" >&2
      exit 2
      ;;
  esac
  codesign_one "$APP_PATH/$REL" "${EXTRA[@]+"${EXTRA[@]}"}" || {
    echo "ERROR: codesign failed on $REL" >&2
    exit 4
  }
  SIGNED=$((SIGNED + 1))
done < "$PLAN"
log "Signed ${SIGNED} nested code objects"

# ── 3. The app itself ───────────────────────────────────────────────────────
codesign_one "$APP_PATH" --entitlements "$ENTITLEMENTS" || {
  echo "ERROR: codesign failed on the app bundle" >&2
  exit 4
}

# ── 4. Verify ───────────────────────────────────────────────────────────────
# --deep --strict walks every nested signature, so an object the plan missed
# fails here rather than as an Invalid notarization later. Authority lines are
# only emitted at -dvvv verbosity; plain -dv omits them entirely.
if ! codesign --verify --deep --strict --verbose=2 "$APP_PATH"; then
  echo "ERROR: signed app failed codesign verification" >&2
  exit 6
fi
AUTHORITY=$(codesign -dvvv "$APP_PATH" 2>&1 | grep "^Authority=" | head -1 || true)
log "App signature: ${AUTHORITY:-<none>}"
if ! echo "$AUTHORITY" | grep -q "Developer ID Application"; then
  echo "ERROR: the app does not carry a Developer ID Application signature" >&2
  exit 6
fi

log "Done. Signed in place: ${APP_PATH}"
