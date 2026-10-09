# Warding Desktop (Electron)

Desktop shell for the Warding web dashboard on macOS, Linux, and Windows
(Windows is in preview — see the build note below). It automatically starts
`warding gateway` and connects to `localhost:5476`.

## Quick Start

```bash
cd electron
npm install
npx electron .
```

The app will:

1. Reuse an existing gateway if one is already reachable and actually serving
   (`/api/ready` 200) — a gateway draining after `/api/shutdown` still answers
   `/api/status`, so it is never adopted; the app waits for the port to clear
   and spawns fresh instead
2. Launch `warding gateway` when needed
3. Show a loading screen while the backend boots. A live bundled backend gets an
   extended Windows cold-start window; a child that actually exits still fails
   immediately with its launch-log cause.
4. Load the dashboard
5. Point the user at Kiro CLI installation and sign-in on the gateway host when
   either prerequisite is missing

The Electron shell uses the same gateway-hosted setup screen as every browser;
it has no separate installer or login runner, and it performs neither step. The
screen links out to <https://kiro.dev/cli/> for the CLI, and names the commands
the user runs to sign in: `kiro-cli login` for a personal account, or
`kiro-cli login --use-device-flow --license pro` for organization SSO. Both are
shown because the portal the bare command opens offers a free Builder ID
alongside organization SSO, and picking the wrong one still succeeds — the
mismatch only surfaces later as missing models. The app observes completion
through the read-only `kiro-cli whoami` probe. Candidate selection is
fail-closed: a broken higher-priority Kiro CLI is shown as needing repair and is
not skipped in favor of a later candidate. Remote tunnel sessions check the
remote gateway host.

## Install as macOS App

Build a native `.app` bundle and install to `/Applications`:

```bash
cd electron
npm install
npx electron-builder --mac --dir
APP_DIR=$([ "$(uname -m)" = "arm64" ] && echo "dist/mac-arm64" || echo "dist/mac")
sudo rm -rf /Applications/Warding.app
sudo cp -R "$APP_DIR/Warding.app" /Applications/Warding.app
```

Launch via Spotlight (Cmd+Space → "Warding"), Dock, or `open /Applications/Warding.app`.
Right-click the Dock icon → Options → Keep in Dock to pin it.

## Build `.dmg`

```bash
npm run dist
```

Output goes to `electron/dist/`. The DMG opens to a branded 660×420 logical-size
drag-to-Applications layout on a flat ground carrying the brand artwork, with
one chevron pointing from the app to `/Applications`.
Its background is a multi-resolution TIFF with 1× and Retina 2× representations.
The release workflow uses this Electron-built DMG as a layout template, removes
its unsigned app, and inserts the signed/stapled app before the DMG itself is
signed and notarized. That keeps local previews and shipped downloads aligned.

## Build Windows Installer (NSIS)

The Windows desktop build is wired end to end: `package.json` declares an
`nsis` target under `build.win`, and `packaging/build-desktop.sh` has a full
Windows branch. Run it from Git Bash (or MSYS/Cygwin — the script normalizes
those to `windows`) at the repo root:

```bash
bash packaging/build-desktop.sh
```

Notes:

- **The build must run natively on Windows**, not cross-built from macOS or
  Linux: the script provisions a Windows python-build-standalone interpreter
  via `uv` and executes its `python.exe` to install and verify the bundled
  backend, then runs `electron-builder --win` to produce the NSIS installer.
- **Signing is optional for a local build.** electron-builder signs natively
  when `WIN_CSC_LINK` and `WIN_CSC_KEY_PASSWORD` name a code-signing
  certificate and its password, and builds a working unsigned installer when
  they are empty. Certificate setup and rotation are in
  [`docs/build/signing-runbook.md`](../../docs/build/signing-runbook.md).
- The result is an assisted (non-one-click, per-user) NSIS installer,
  `Warding Setup <version>.exe` (nightly builds:
  `Warding Nightly Setup <version>.exe`), in `website/electron/dist/`.
- The pinned electron-builder NSIS template is patched during `npm install` to
  expose Warding's staged-payload publish hook. On a normal same-volume
  per-user install it renames the large `resources` / `locales` trees into place
  and copies only the small root remainder; per-machine installs keep the
  upstream copy path so files inherit the Program Files ACL. Cross-volume or
  occupied destinations also retain the upstream copy-and-retry fallback. The
  Windows backend ships checked-hash
  bytecode for the measured gateway import closure, so first launch consumes
  build-time caches rather than generating thousands of files under Defender.
- The native welcome/finish sidebar and the header used on intermediate pages
  carry the brand logo and artwork. The standard NSIS controls and
  localized instructions remain native. Page boundaries use a short Win32
  alpha-blended cross-fade that follows the system client-area animation setting;
  extraction itself stays on the native progress page without timer-driven art.

See `../../docs/guides/windows-install.md` for the CI-built installer and the
current Windows support status.

## Updating

After pulling new code and rebuilding (`npm run build`):

```bash
# Rebuild and reinstall the desktop app
cd electron && npx electron-builder --mac --dir
APP_DIR=$([ "$(uname -m)" = "arm64" ] && echo "dist/mac-arm64" || echo "dist/mac")
sudo rm -rf /Applications/Warding.app
sudo cp -R "$APP_DIR/Warding.app" /Applications/Warding.app

# Restart the gateway (if using Launch Agent)
launchctl stop dev.warding.gateway
launchctl start dev.warding.gateway
```

## Uninstall

```bash
# Remove the desktop app
sudo rm -rf /Applications/Warding.app

# Remove the Launch Agent (if configured from main README)
launchctl unload ~/Library/LaunchAgents/dev.warding.gateway.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/dev.warding.gateway.plist
```

## Remote Tunnel Mode (Headless Remote Host)

If the gateway runs on a remote host (the recommended setup per
`../../docs/guides/remote-and-mobile.md`), the app can fetch tokens automatically
via SSH instead of reading the local `.local_secret`.

### Prerequisites

1. An SSH tunnel forwarding the remote gateway port to localhost:
   ```bash
   ssh -L 5476:localhost:5476 YOUR_HOST.example.com
   ```
   Or use a macOS LaunchAgent (see `../../docs/guides/assets/`).

2. `warding` installed on the remote host. The default auto-discovers across common
   install layouts — no configuration needed unless you installed somewhere unusual.

### Configure

Remote host settings are **per-port** — each tab can have its own remote host
(or none, for local gateways). Focus the tab you want to configure, then use
**Tab menu → Set Remote Host…** or right-click the tab bar:

1. The modal shows which port it's configuring (e.g. "Remote host for :5476")
2. Enter your remote host's hostname or SSH config alias (e.g. `myhost.example.com` or `workhost`)
3. Leave the binary path at the default unless you installed warding somewhere
   unusual. The default tries, in order:
   - `~/.local/bin/warding` (install.sh / source install)
   - `~/.warding-app/.venv/bin/warding` (one-liner installer venv)
4. Optionally set a **Remote port** if the gateway port on the remote host differs
   from the local tab port (default: same as tab port)
5. Optionally set a **Remote PATH** if warding needs additional directories
   (default: `~/.local/bin:/usr/bin:/bin`)
6. Click Save. Leave hostname empty to clear (use local token for that port).

**Multi-instance example:**
- Tab 1 on `:5476` — local gateway, no remote host needed
- Tab 2 on `:7778` — SSH tunnel to another host, remote host configured

The app will SSH into the configured remote host and run `warding token` on
each launch to get a fresh JWT — no manual paste required.

### Token flow (per tab)

```
1. Try local ~/.warding/.local_secret → /api/token/local on the tab's port
2. If remote host configured for this port:
   SSH: export PATH=<remotePath> WARDING_PORT=<port>; <bin> token
3. Fallback: show manual token prompt
```

### Menus

| Location | Item | Action |
|----------|------|--------|
| Tab menu / tab bar right-click | Set Remote Host… | Configure hostname for the **focused tab's** port |
| Tab menu / tab bar right-click | Refresh Token (⌘⇧T) | Fetch a fresh token for the **focused tab** |
| Tab menu / tray | Open Config File | Open `config.json` in default editor |

### Tab naming

Tabs default to `[:port]`. You can set a **default name** per port via
**Rename Tab → ☑ Set as default name**. New tabs on that port will use it
automatically. Names are stored in `remoteHosts[port].defaultName`.

### Config file

Settings are persisted via `electron-store` in
`~/Library/Application Support/Warding/config.json`:

```json
{
  "remoteHosts": {
    "5476": {
      "host": "myhost.example.com",
      "binPath": "~/.local/bin/warding",
      "remotePort": "",
      "remotePath": "",
      "defaultName": "Cloud"
    }
  },
  "sshTimeoutMs": 20000
}
```

Open via **Tab menu → Open Config File** or tray menu.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| "SSH token fetch failed" | Check `ssh YOUR_HOST` works from Terminal |
| "warding binary not found in any of …" | Install warding (`pip install warding`), or set a custom path |
| "command not found: kiro-cli" | Set Remote PATH to include the directory holding `kiro-cli` (the default covers `~/.local/bin`) |
| "command not found: dirname" | Remote PATH missing `/usr/bin` — reset to default or add it |
| Token fetched but 403 | Gateway may need restart — `ssh host systemctl --user restart warding` |
| Wrong tab refreshed | Focus the target tab first (use Tab menu, not tray) |

## Notes

- Closing the window hides to tray — right-click the tray icon or Cmd+Q to quit
- External links open in your default browser
- Desktop leaves the child `PATH` unchanged; the gateway-side prerequisite
  service independently probes Kiro CLI's supported user-local, Homebrew,
  macOS app-bundle, and Windows MSI locations
