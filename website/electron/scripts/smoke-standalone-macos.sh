#!/bin/bash
set -euo pipefail

app="${1:?Pass the path to a locally signed Warding.app}"
app="$(cd "$app" && pwd -P)"
port=15476
if lsof -nP -tiTCP:"$port" -sTCP:LISTEN >/dev/null; then
  echo "Port $port is in use. Quit that instance before running this smoke test." >&2
  exit 1
fi
codesign --verify --deep --strict "$app"

scratch="$(mktemp -d /tmp/warding-mac-smoke.XXXXXX)"
app_pid=""
gateway_pid=""
cleanup() {
  for pid in "$gateway_pid" "$app_pid"; do
    [ -z "$pid" ] || kill -TERM "$pid" 2>/dev/null || true
  done
  if [ -n "$app_pid" ]; then wait "$app_pid" 2>/dev/null || true; fi
  echo "Smoke test logs: $scratch"
}
trap cleanup EXIT

env -u WARDING_HOME -u WARDING_PORT -u KIRO_HOME HOME="$scratch" \
  WARDING_TELEMETRY_DISABLED=1 WARDING_SKIP_MODEL_DOWNLOAD=1 \
  "$app/Contents/MacOS/Warding" "--user-data-dir=$scratch/electron" \
  >"$scratch/desktop.log" 2>&1 &
app_pid=$!

for ((attempt = 0; attempt < 90; attempt++)); do
  kill -0 "$app_pid"
  if curl --noproxy '*' -fsS --max-time 2 "http://127.0.0.1:$port/api/ready" 2>/dev/null |
    jq -e '.ready == true' >/dev/null; then
    break
  fi
  sleep 0.5
done
curl --noproxy '*' -fsS --max-time 2 "http://127.0.0.1:$port/api/ready" |
  jq -e '.ready == true' >/dev/null
listener="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN)"
[ "$(ps -p "$listener" -o ppid= | tr -d ' ')" = "$app_pid" ]
gateway="$(ps -p "$listener" -o comm=)"
case "$gateway" in
  "$app/Contents/Resources/backend-dist/"*) gateway_pid="$listener" ;;
  *) echo "The listener is outside the app bundle" >&2; exit 1 ;;
esac
test -f "$scratch/.warding-desktop/config.json"
test -f "$scratch/.warding-desktop/kiro/agents/warding.json"
test ! -e "$scratch/.kiro/agents/warding.json"

ambient_mcp="$scratch/.kiro/settings/mcp.json"
desktop_mcp="$scratch/.warding-desktop/kiro/settings/mcp.json"
mkdir -p "${ambient_mcp%/*}" "${desktop_mcp%/*}"
printf '%s\n' '{"mcpServers":{"ambient-smoke":{"command":"/usr/bin/true","disabled":true}}}' \
  >"$ambient_mcp"
cp "$ambient_mcp" "$scratch/ambient-original.json"
printf '%s\n' '{"mcpServers":{"desktop-smoke":{"command":"/usr/bin/true"}}}' >"$desktop_mcp"

curl --noproxy '*' -fsS --max-time 5 \
  -H 'Content-Type: application/json' \
  -d '{"name":"desktop-smoke","enabled":false}' "http://127.0.0.1:$port/api/mcp/toggle" |
  jq -e '.ok and (.enabled == false)' >/dev/null
curl --noproxy '*' -fsS --max-time 5 "http://127.0.0.1:$port/api/mcp" |
  jq -e 'any(.[]; .name == "desktop-smoke" and (.enabled == false))
    and all(.[]; .name != "ambient-smoke")' >/dev/null
jq -e '.mcpServers["desktop-smoke"].disabled == true' "$desktop_mcp" >/dev/null
cmp "$ambient_mcp" "$scratch/ambient-original.json"
test ! -e "${ambient_mcp%.json}.lock"

env -u PYTHONDONTWRITEBYTECODE -u PYTHONPYCACHEPREFIX WARDING_HOME="$scratch/.warding-desktop" \
  "${gateway%/*}/warding" --version
codesign --verify --deep --strict "$app"
echo "The app started its bundled gateway on port $port with a fresh data directory."
