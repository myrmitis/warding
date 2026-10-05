#!/usr/bin/env bash
# sign-dmg.sh -- Developer ID sign a DMG in place.
#
# hdiutil-created DMGs carry an adhoc signature, which the Apple notary
# service Accepts but Gatekeeper rejects ("app is damaged" when dragging
# the app out of a quarantined mount). A Developer ID signature on the DMG
# itself fixes that -- and additionally makes the DMG staple-able, so
# first-install verification works fully offline (stapler fails with
# Error 73 on unsigned DMGs).
#
# Usage: sign-dmg.sh <dmg-path>
#
# Environment:
#   SIGNING_IDENTITY  (required) the same identity sign.sh signs the app with
#   SIGNING_KEYCHAIN  (optional) the keychain holding it, as in sign.sh
#   DMG_IDENTIFIER    (optional) the code identifier to sign under. The release
#                     workflow passes the app's CFBundleIdentifier so the
#                     image's signature names the product rather than its
#                     filename; unset, codesign derives one from the filename.
#
# A disk image takes neither entitlements nor the hardened runtime flag; it
# carries a plain Developer ID signature with a secure timestamp.
#
# Exit codes: 0 signed and verified; 1 usage or environment error;
# 4 codesign failed; 6 verification failed.

set -euo pipefail

DMG_PATH="${1:-}"

if [ -z "$DMG_PATH" ]; then
  echo "Usage: $0 <dmg-path>" >&2
  exit 1
fi
if [ ! -f "$DMG_PATH" ]; then
  echo "ERROR: DMG not found at $DMG_PATH" >&2
  exit 1
fi
if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERROR: codesign is macOS-only; run this on a macOS host" >&2
  exit 1
fi
: "${SIGNING_IDENTITY:?Set SIGNING_IDENTITY}"

log() { printf '\033[1;36m▶ %s\033[0m\n' "$*"; }

CODESIGN_ARGS=(--force --timestamp --sign "$SIGNING_IDENTITY")
if [ -n "${SIGNING_KEYCHAIN:-}" ]; then
  CODESIGN_ARGS+=(--keychain "$SIGNING_KEYCHAIN")
fi
if [ -n "${DMG_IDENTIFIER:-}" ]; then
  CODESIGN_ARGS+=(--identifier "$DMG_IDENTIFIER")
fi

log "Signing $(basename "$DMG_PATH")..."
if ! codesign "${CODESIGN_ARGS[@]}" "$DMG_PATH"; then
  echo "ERROR: codesign failed on the DMG" >&2
  exit 4
fi

# ── Fail-closed signature gate ──────────────────────────────────────────────
# The DMG must now carry a VALID Developer ID signature (an adhoc or missing
# signature reproduces the "app is damaged" defect).
# Authority lines are only emitted at -dvvv verbosity; plain -dv omits them
# entirely, which would make this gate reject every valid DMG.
if ! codesign --verify --strict "$DMG_PATH" 2>&1; then
  echo "ERROR: signed DMG failed codesign verification -- failing closed." >&2
  exit 6
fi
AUTHORITY=$(codesign -dvvv "$DMG_PATH" 2>&1 | grep "^Authority=" | head -1 || true)
log "DMG signature: ${AUTHORITY:-<none>}"
if ! echo "$AUTHORITY" | grep -q "Developer ID Application"; then
  echo "ERROR: signed DMG does not carry a Developer ID signature -- failing closed." >&2
  codesign -dvvv "$DMG_PATH" 2>&1 | head -8 >&2 || true
  exit 6
fi

log "Signed DMG in place: ${DMG_PATH} ($(du -h "$DMG_PATH" | cut -f1))"
