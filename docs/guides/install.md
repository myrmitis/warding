# Installing and running Junction

This guide covers every way to install Junction, the first-run setup, how to
verify the install, and how to troubleshoot the failures that actually happen.

Builds use plain `pip` + `npm`/Vite + `pytest`, driven by the repo-root
[`Makefile`](../../Makefile). There is no proprietary build tooling.

> **Platforms: macOS, Linux, and Windows.** macOS and Linux use the `Makefile` /
> `setup.sh` paths below. Windows runs natively from a Python source install
> (`pip install -e ".[voice]"`, launched via `python -m junction up` or
> `junction up`); all POSIX-only process, signal, file-lock and metrics calls
> route through `junction.platform_compat`. See
> [windows-install.md](windows-install.md) for the Windows walkthrough.

---

- [Prerequisites](#prerequisites)
- [Install paths](#install-paths)
- [Build targets](#build-targets)
- [First run](#first-run)
- [Configuration](#configuration)
- [Verify the install](#verify-the-install)
- [Running as a service](#running-as-a-service)
- [Linux: the agent sandbox and unprivileged user namespaces](#linux-the-agent-sandbox-and-unprivileged-user-namespaces)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)
- [Removing user data](#removing-user-data)
- [Clean reinstall](#clean-reinstall)
- [Data retention details](#data-retention-details)
- [Next steps](#next-steps)

---

## Prerequisites

| Requirement | Needed for | Floor |
|-------------|------------|-------|
| **Python** | Backend | `>= 3.10` (`requires-python` in `pyproject.toml`; `make build` provisions a 3.12 `.venv` by default) |
| **Node.js + npm** | Building the dashboard | `20 \|\| >= 22` (`website/package.json` `engines`); `ensure-node.sh` targets 20, and drops to 16 on Amazon Linux 2 where newer official builds need a glibc that host does not have |
| **An ACP runtime** | Driving the LLM | Optional; Cursor, Claude, Codex, Grok, … — a vendor agent CLI is optional |

Node is only needed to *build* the dashboard. A source install that already
has `website/dist` staged does not need Node at runtime. Local desktop
artifacts from `make desktop` also bundle the dashboard.

### Agent backend (optional)

Junction drives an LLM through an ACP runtime from the harness-plane registry.
`agent.provider` is `acp`. `agent.acp_backend` defaults to `auto`: Junction
docks the first installed of Cursor, Claude, Codex, and the rest. A vendor
agent CLI is optional — install one only when you want that harness.

If no runtime is on `PATH`, spawning a session waits until you dock one. On
the first dashboard launch the **Dock an agent** page walks through picking a
runtime. `junction doctor --quick` reports the composed planes, including
which runtimes are available.

### Embeddings: nothing to install

Semantic memory and the knowledge library need no setup step. Embeddings run
**in-process** through the vendored llama-cpp-python runtime, so there is no
separate server and no HTTP hop. On first start the gateway downloads the
Qwen3-Embedding-0.6B GGUF (about 610 MB) in the background over HTTPS, verifies
it against a pinned sha256, and installs it under `~/.junction/models/`.

While the model is absent (first boot, download in flight, or a failed
download), memory search degrades to keyword/FTS search and picks embeddings up
automatically once the model lands, with no gateway restart. Two escape
hatches exist for mirrored or airgapped installs:

- `JUNCTION_EMBED_MODEL_URL` (or `memory.embed_model_url`) points the download
  at a mirror. The sha256 pin still verifies whatever it fetches.
- `JUNCTION_EMBED_MODEL_PATH` (or `memory.embed_model_path`) runs a local GGUF
  of your own instead. In that mode the default model is never downloaded.

`memory.embedding_provider` accepts only `llama_cpp`; any other value in an old
config is coerced to it on load.

## Install paths

### Which path on Linux

**Start with the operator script** on macOS and Linux. It needs Python 3.10+
and Node.js 22+. It clones this repository (it is not a release CDN), runs
[`minimal_install.sh`](../../minimal_install.sh), and links `junction`. Read
[`scripts/get-junction.sh`](../../scripts/get-junction.sh) before you run it.

```bash
curl -fsSL https://raw.githubusercontent.com/laqaer/junction/main/scripts/get-junction.sh | sh
junction setup
junction up
```

Use a **source checkout** when you are changing Junction. Install a
**desktop package** (`.deb` / `.rpm`) from a local `make desktop`
when you want the things only the Electron shell provides: an application-menu
entry and icon, a native window with persisted geometry, a dock/taskbar badge,
a system-wide hotkey to summon the dashboard, a gateway that starts and stops
with the app, and in-app updates. Those packages install to a fixed path under
`/opt`, which is what makes `junction service install` — and therefore the
[AppArmor profile](#linux-the-agent-sandbox-and-unprivileged-user-namespaces)
the agent sandbox needs on Ubuntu 23.10+ — reachable from a desktop artifact.

The **AppImage** stays available for hosts where you cannot install a system
package (no root, an unsupported distro). It needs FUSE present, and because it
runs from a randomized temporary mount there is no durable path to attach an
AppArmor profile to or to point a `junction` launcher at — so on a distro that
restricts unprivileged user namespaces it needs the extra manual step described
in the sandbox section. Prefer a package where you can.

| You want | Use |
|---|---|
| The dashboard, a terminal, scheduled work, a server | **Operator script** (above) or **from source** (a) |
| A desktop app on Debian/Ubuntu | **`.deb`** (d) |
| A desktop app on Fedora / RHEL / CentOS Stream / Amazon Linux 2023 | **`.rpm`** (d) |
| A desktop app with no root and no package manager | **AppImage** (d) |
| A container host | **Docker** ([guide](docker.md)) |

### a. From source (development)

Clone, build the dashboard, install the backend, then compose both planes:

```bash
git clone https://github.com/laqaer/junction.git
cd junction
python3 -m venv .venv && source .venv/bin/activate
cd website && npm install && npm run build && cd ..
pip install -e ".[dev]"
junction setup
junction doctor --quick
junction up
```

`make build` does the frontend + editable backend install into `.venv` in one
step. On Windows the same targets run through `make.ps1`.

### b. From source (Makefile / make.ps1)

Build the dashboard, install the backend into a local virtualenv (`.venv`), and
run the gateway straight out of `src/`:

```bash
make build                                   # npm build + editable backend install into .venv
PYTHONPATH=src python -m junction up   # -> http://localhost:5476
```

On Windows the same targets run through `make.ps1`, because `make` is not part
of a Windows install and the Makefile's recipes are POSIX-shaped
(`.venv/bin/pip`, `rm -rf`, `cp -R`, `bash ensure-*.sh`):

```powershell
.\make.ps1 build                             # same two steps, same artifacts
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m junction up
```

The venv interpreter is named explicitly rather than a bare `python`: the
dependencies live only in `.venv`, and on Windows a bare `python` resolves to the
system interpreter (or the Microsoft Store alias stub), which would fail at
import. `.\.venv\Scripts\Activate.ps1` first is the other way, after which
`python` and `junction` both resolve inside the venv.

The two drivers expose the same target set, and
`test/test_build_target_parity.py` fails the build if one gains a target the
other lacks. Differences are confined to what the platform forces: a Windows
venv puts its executables in `.venv\Scripts\`, and the macOS-only
`resign-macos-libs.sh` step has no Windows counterpart.

`make build` runs two steps:

1. **`frontend`**: `npm ci` (or `npm install`) + `npm run build` in `website/`,
   then copies `website/dist` into `src/junction/static/dist` so the backend
   serves the SPA.
2. **`backend`**: creates `.venv` and runs an editable install with the `dev`
   extra (`pip install -e ".[dev]"`).

Both targets bootstrap their toolchain first (`ensure-node.sh`,
`ensure-python.sh`) and fall back to whatever is on `PATH` if that fails. The
backend target refuses to build a venv from an interpreter older than 3.10
rather than letting the install backtrack forever.

`make.ps1` resolves the same toolchain but installs none of it: the bootstrap
scripts' install paths are `curl … | sh`, so on Windows it searches (`py`
launcher first, then `PATH`, skipping the Microsoft Store alias stub) and prints
the `winget` command to run if nothing usable is found. It honors the same
`<data-home>/python-bin` and `node-bin-dir` markers those scripts record. The
`desktop` and `backend-bin` targets are the exception: they delegate to
`packaging/build-desktop.sh`, which provisions its own `uv` and
python-build-standalone interpreter on every platform.

After the backend target runs, `bin/junction` resolves its real install root,
sets `JUNCTION_PROJECT_DIR`, and delegates to `.venv/bin/junction`. That console
script comes from the editable package metadata (`junction._bootstrap:main`),
so the virtual environment makes `src/junction` importable without the wrapper
modifying `PYTHONPATH`; caller-provided entries pass through unchanged.

Any CLI subcommand works the same way, for example
`PYTHONPATH=src python -m junction setup` or `... doctor`.

The equivalent by hand:

```bash
git clone https://github.com/laqaer/junction.git
cd junction
cd website && npm install && npm run build && cd ..
pip install -e ".[voice]"    # [voice] adds the optional speech-to-text extras
```

### c. Self-contained pip wheel

Produce a wheel that bundles the pre-built dashboard, then install it anywhere
with a suitable Python:

```bash
make wheel                # builds the frontend, then python -m build --wheel -> dist/
pip install dist/*.whl
junction up                 # -> loopback dashboard
```

Junction is pure Python, so the wheel is platform-independent:
`dist/junction-<version>-py3-none-any.whl` (for example
`junction-0.1.2-py3-none-any.whl`). One wheel serves every OS. The dashboard is
folded in by the custom `BuildWithFrontend` build step in
[`setup.py`](../../setup.py), which also bundles `CHANGELOG.md` so the
dashboard's changelog view works on a wheel install with no source tree.

The pip install name is **`junction`**; the import package is `junction`;
the user-facing CLI is **`junction`**, the only console script:

| Command | Entry point |
|---------|-------------|
| `junction` | `junction._bootstrap:main` |

`pyproject.toml`'s `[project.scripts]` declares it. Because a `[project]`
table exists, setuptools reads the entry points from there and ignores
`setup.cfg`'s `console_scripts`.

Optional extras (install with e.g. `pip install "junction[voice]"`):

| Extra | Adds | For |
|-------|------|-----|
| `voice` | `boto3`, `amazon-transcribe` | Speech-to-text transcription |
| `otlp` | `opentelemetry-exporter-otlp-proto-http` | OTLP/HTTP metrics export. Installing it does not enable egress; that still needs an explicit `telemetry.otlp_endpoint` |
| `perf` | `py-spy` | Out-of-process profiling (`junction perf sample --pid`). The in-process sampler needs nothing extra |
| `teams` | `PyJWT[crypto]` | Microsoft Teams channel (validates the inbound Bot Framework RS256 JWT) |
| `dev` | pytest, black, isort, flake8, mypy, ... | Contributor tooling; what `make build` installs |

`make desktop` and `make backend-bin` need no extra: both run
`packaging/build-desktop.sh`, which provisions a python-build-standalone
interpreter and pip-installs the project into it.

### d. Bundled desktop app

A double-clickable app that embeds a python-build-standalone (PBS) interpreter
plus uv-installed deps inside an Electron shell. End users need no Python, pip,
npm, or Node:

```bash
make desktop
```

Output is a DMG (plus a zip) on macOS, an AppImage plus a `.deb` and an `.rpm`
on Linux, and an assisted NSIS Setup.exe on Windows, under
`website/electron/dist/`. The macOS DMG opens to a branded
drag-to-Applications layout carrying the opening animation's artwork. The
Windows wizard keeps native controls and its
per-user default while carrying matching Junction artwork through its sidebar
and header. On macOS the default is ONE universal DMG: the Electron shell is
lipo-merged, and the backend, which cannot be lipo-merged, ships as two complete
PBS trees selected at launch by `process.arch`. The x86_64 backend is built
under Rosetta 2, so a universal build needs an Apple-Silicon host;
`UNIVERSAL=0` forces a faster host-arch-only build. Linux is always host-arch,
and the three Linux formats come from one backend tree packaged three times.

#### Installing a Linux desktop package

```bash
sudo apt install ./Junction-x86_64.deb     # Debian, Ubuntu
sudo dnf install ./Junction-x86_64.rpm     # Fedora, RHEL, CentOS Stream, AL2023
```

Either one installs to `/opt/Junction`, registers the application-menu entry and
MIME database, refreshes the icon cache, links `/usr/bin/junction-desktop`, and —
on a host whose AppArmor supports the bundled profile — installs and loads the
`userns` profile the agent sandbox needs, so no manual `sandbox install-profile`
step is required. The fixed install path is what makes all of that durable.

Updates arrive through the app (**About → Check for updates**), which downloads
the new package and hands it to `dpkg` / `rpm`. That needs root, so expect one
elevation prompt (`pkexec` or `sudo`) at install time — it is the package
manager doing the write, not the app. `sudo apt remove junction` /
`sudo dnf remove junction` uninstalls; see
[Uninstalling](#uninstalling) for what happens to your data.

The AppImage needs no root and no package manager, which is the reason to pick
it, but it also needs FUSE present (`sudo dnf install fuse` on Amazon Linux
2023, which ships without it; `--appimage-extract-and-run` is the escape hatch)
and it runs from a randomized temporary mount, so it carries the manual
sandbox-profile step and the move-breaks-it caveat documented in the
[sandbox section](#linux-the-agent-sandbox-and-unprivileged-user-namespaces).

All three Linux formats are built from the same glibc floor as the build runner.
Verified requirement at the time of writing is **glibc 2.34**, which covers
Ubuntu 22.04+, Debian 12+, Fedora, CentOS Stream 9 and Amazon Linux 2023, and
excludes Ubuntu 20.04, Debian 11 and Amazon Linux 2 — on those, use the
[source install](#a-from-source-recommended) instead.

Prebuilt downloads for the release channels are linked from the
[README](../../README.md#app-downloads). The Windows desktop installer remains
a preview artifact; see [windows-install.md](windows-install.md) for its current
publishing and signing status. The source install remains the fully supported
Windows path.

See [desktop-app.md](../build/desktop-app.md) for the full pipeline (frontend,
PBS provisioning, pip install, pruning, electron-builder) and how the app
locates and launches the bundled backend.

### e. Docker

For always-on servers the gateway also ships as a public multi-arch image on
GHCR. See [docker.md](docker.md).

## Build targets

Every target has the same name on both drivers: `make <target>` on macOS and
Linux, `.\make.ps1 <target>` on Windows.

| Target | What it does |
|--------|--------------|
| `make build` | Frontend (npm/Vite) + backend into `.venv` |
| `make frontend` | Dashboard only: npm build, staged into `src/junction/static/dist` |
| `make backend` | Backend only: `.venv` + editable install with the `dev` extra |
| `make wheel` | Self-contained pip wheel with the dashboard bundled, into `dist/` |
| `make backend-bin` | Frozen standalone backend binary (host arch only) |
| `make desktop` | Full desktop app: DMG on macOS, AppImage on Linux, NSIS installer on Windows |
| `make test` | Build, then run the `pytest` suite |
| `make clean` | Remove build artifacts, dists, and caches |

Override the Python interpreter with `make PY=python3.12 build`, or
`.\make.ps1 build -Py C:\path\to\python.exe`.

Both desktop targets run `packaging/build-desktop.sh` on every platform,
including Windows, where `make.ps1` invokes it through the Git for Windows bash:
the script already normalizes MSYS `uname` output and has a Windows PBS branch,
and CI's Windows lane calls it the same way. The plain `build` path needs no
bash. Note that a locally built Windows installer is **unsigned** — only CI's
signing lane has the signing identity — so SmartScreen shows an "unrecognized
app" interstitial.

## First run

After installing by any path:

```bash
junction setup            # writes the first-run marker
junction doctor --quick   # compose both planes without serving
junction up               # compose, then serve the loopback dashboard
```

From a source checkout, use `PYTHONPATH=src python -m junction <subcommand>`
in place of `junction`. `junction gateway` is the same server as `junction up`
and remains for scripts.

### What a successful test looks like

`junction doctor --quick` composes both planes and does not start the
catalog. Before `junction up`, the model line is:

```text
  model:   down (starts with junction up; gateway still works)
```

`junction up` prints a compose banner on stderr, then serves the dashboard
on loopback (default `http://127.0.0.1:5476`):

```text
Junction compose
  harness: auto (selected=<id or none installed>; vendor CLI optional)
  model:   built-in catalog (provider translation is not bundled)
  roles:   orchestration=economy planning=capable execution=standard
never paste provider keys into chat.
```

`selected=` names an ACP runtime already on the machine, or `none installed`.
The roles line is the unpinned cost classes. A pin in `agent.role_models`
still wins.

Then:

1. Open the dashboard. Dock an ACP runtime you already installed. Chat uses
   that harness's own model. The default pin is `auto`.
2. `junction planes` prints the same compose lines under the heading
   `Junction planes`.
3. `junction router catalog` lists namespaced slugs and says
   `no credentials in this snapshot`.
4. `junction router plan` prints the role DAG.
5. `junction router status` prints `model plane: degraded (gateway still works)`.
   Degraded is expected: the catalog is up and the translation port `:4200`
   is not bundled. The keys line is `never paste provider keys into chat.`
6. Probe the listener (port `4202`, or `MODEL_ROUTER_PORT` /
   `CODEX_ROUTER_PORT` when set):

```bash
curl -s http://127.0.0.1:4202/health
curl -s http://127.0.0.1:4202/catalog
curl -si -X POST http://127.0.0.1:4202/v1/chat/completions
```

Health is `{"ok":true,"status":"ok","service":"junction"}`. Catalog is the
shipped snapshot. The POST is HTTP 501 with
`{"ok":false,"code":"model_router_no_forward"}`. A busy `4202` is left
alone; probe whatever already owns it instead of starting a second listener.

### Route work across your subscriptions

Chat sessions run the one agent `agent.acp_backend` names. Work handed to a
spawned subagent can go to whichever installed coding agent you already pay for
is best placed to do it: Claude Code, Codex (ChatGPT), Cursor, Grok Build, and
OpenCode (OpenRouter and any other provider it logs into). The router picks an
agent and never forwards provider traffic; each agent keeps its own login and
Warding never sees a key. kiro-cli is optional. The router and OpenCode are
registered and unit-tested; neither is verified on a live run yet.

1. `junction up` and open the dashboard. On first run, the setup screen lists
   your agents; after that they live in **Settings ▸ Agents & plans**.
2. For each agent: **Install** (if it is missing), then **Sign in**. Both run
   the agent's own command in the dashboard terminal: `claude auth login`,
   `codex login`, `cursor-agent login`, `grok login`, `opencode auth login`
   (choose OpenRouter there). Then **Check**: the agent is started once, with
   no prompt, and shows **Connected** or what it still needs.
3. On first run, **Continue with these agents** opens the dashboard once any
   agent is connected.
4. Per agent, set **Billing**, **Plan size** (relative size of the plan), and
   **Tasks per window** if you know the plan's limit. **Who gets what** shows
   where each kind of work goes right now.

The same from a terminal: `warding route check`, `warding route`, and
`warding route run -k review "review the diff on this branch"`. Ask the
dashboard agent to fan a plan out and it calls `spawn_run` with
`harness="route"` and a `kind` per step (from chat, that needs a chat harness
that carries Warding's MCP tools, which today is kiro-cli). Work that hits a usage limit before
doing anything moves to the next agent on its own.

How lanes are scored and when work fails over:
[harness-router](../system-specs/modules/harness-router.md).

### What `junction setup` asks

The wizard installs the agent config, then walks through the workspace
directory, timezone, dashboard URL, and (on macOS) the desktop app. It does NOT
configure any messaging channel: pass `--slack` to opt into the guided Slack
credential and slash-command setup. It also does NOT install a browser: browsing
is available when `playwright-cli` is on PATH, and you install it separately (see
[Browser](#browser)).

**Want the Playwright CLI at your own shell?** That is a separate tool from the
Browser Mode above, and it has its own installer, which bootstraps Node when your
machine has none and reports enterprise-registry failures (mirror login, proxy,
blocked browser CDN) as specific remedies rather than a raw npm dump:

```bash
curl -fsSLO https://raw.githubusercontent.com/laqaer/junction/main/playwright-cli.sh
less playwright-cli.sh          # read it before you run it
sh playwright-cli.sh --version 0.1.18
```

The download-and-read form is listed first on purpose: piping a script into a
shell is prohibited on many corporate machines, and `raw.githubusercontent.com`
itself is blocked or rate-limited on some — which is the same audience whose
network this script exists to cope with. If yours allows it, `curl -fsSL … | sh`
works as a one-liner; if it does not, take the file from a checkout or a release
and run it locally. Either way the script reaches only three hosts: the npm
registry (or the mirror you point it at), the Node mirror when it has to
bootstrap a toolchain, and the Playwright CDN for the browser binaries — that
last one only unless you pass `--skip-browsers`, and `--download-host` points it
at an internal mirror instead.

Windows uses `playwright-cli.ps1` with the same flags in PowerShell spelling.
`--help` lists all of them; `--dry-run` prints the plan without changing anything.
Design notes and the exit-code table:
[browser module spec](../system-specs/modules/browser.md).

**Messaging channels are optional.** The default wizard configures none, and the
web dashboard is fully functional without any messaging credentials. Connect a
channel later -- Slack (`junction setup --slack` or
[slack-setup.md](slack-setup.md)),
[Discord](../../src/junction/docs/discord-integration.md),
[Telegram](../../src/junction/docs/telegram-integration.md),
[Teams](../../src/junction/docs/teams-integration.md),
[Webex](../../src/junction/docs/webex-integration.md),
[WeCom](../../src/junction/docs/wecom-integration.md),
[WeChat](../../src/junction/docs/weixin-integration.md), or
[WhatsApp](../../src/junction/docs/whatsapp-integration.md) --
when you want to reach the same agent away from your desk.

These flags narrow the wizard:

| Flag | Effect |
|------|--------|
| `--agent-only` | Install the agent config and stop, skipping the workspace and every credential prompt |
| `--slack` | Run the guided Slack credential + slash-command setup (opt-in) |
| `--clean` | Fresh agent config: ignore the existing `junction.json` and regenerate from defaults instead of merging your MCP servers and tools forward |
| `--electron-only` | Install only the macOS desktop app |

The two combine: `junction setup --agent-only --clean` rebuilds the agent config
from scratch and touches nothing else. That is the fix for a broken or stale MCP
configuration, because without `--clean` the existing file is used as the base
so all user customizations survive.

## Browser

Browsing is optional and installed separately. The agent drives a browser by
running `playwright-cli` commands, so it needs Node.js 20 or newer:

```bash
npm install -g @playwright/cli@latest
playwright-cli install-browser              # --with-deps on Debian/Ubuntu only
playwright-cli install --skills agents --global
```

`--with-deps` installs OS libraries through `apt` and needs root. Playwright
implements it for apt alone, so on Fedora, RHEL, CentOS or Amazon Linux it
misfires against Ubuntu package names; install the libraries with your own
package manager instead. The Settings → Browser install button adapts to the
host and reports the command to run when it needs root — see
[the browser module spec](../system-specs/modules/browser.md#os-dependencies).

The dashboard's **Browser** panel embeds the CLI's own dashboard over loopback,
which shows the live session and lets you take over with real mouse and keyboard.
That is how you complete a CAPTCHA or a 2FA prompt, and how you log in once so a
session can be captured with `playwright-cli state-save`.

**Installing the CLI makes browsing available; it does not auto-approve it.**
There is no separate capability toggle because the CLI has no way to expose only
a subset of its verbs. Every `playwright-cli` shell command still follows the
ordinary approval flow. Under normal mode the first command prompts; you can
approve once, trust its command pattern for the session, or deliberately enable a
wider trust mode. This matters most for `playwright-cli attach --extension`, which
drives your own running Chrome with the sessions you are already logged into.

## Configuration

- Config file: `~/.junction/config.json`, managed with
  `junction config get/set/edit`.
- Credentials: `~/.junction/.env` holding messaging-channel tokens (for Slack:
  `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN`, `JUNCTION_OWNER_ID`; other channels use
  their own keys). See [slack-setup.md](slack-setup.md) for creating the Slack
  app.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `JUNCTION_HOME` | `~/.junction` | Data directory (config, credentials, databases) |
| `JUNCTION_PORT` | `5476` | Port the gateway / dashboard listens on |
| `JUNCTION_EMBED_MODEL_URL` | CDN default | Mirror for the embedding model download |
| `JUNCTION_EMBED_MODEL_PATH` | unset | Run a local GGUF instead of the bundled model |

`JUNCTION_PORT` is an environment variable validated at CLI entry, not a config
key. `--port` on the CLI overrides it (`--port auto` binds an OS-assigned
ephemeral port). The `dashboard.url` config key only advertises a remote URL.
For the installed service the port is baked into the unit at install time — see
[Running as a service](#running-as-a-service) for how to set and later change
it.

### The data home is `~/.junction`

Junction stores its data in `~/.junction`. Override that location with
`JUNCTION_HOME`; set it before the first launch when you want a different
directory. There is no other data directory and no fallback.

## Verify the install

The short pass is
[What a successful test looks like](#what-a-successful-test-looks-like):
`junction doctor --quick`, then `junction up`, then the catalog health and
the 501 completion route.

The long pass is:

```bash
junction doctor
```

`doctor` reports, section by section: the composed platform edition, the data
home (including a legacy-home conflict warning), Linux pod session bus, the
project directory, the agent config, configuration values (provider, model,
approval mode, dashboard URL), the managed MCP servers and their tool counts,
the runtime, vector memory and the in-process embedding model (including whether
the model URL is reachable), speech-to-text, the Slack integration,
loop-stall crash dumps, and connectivity.

## Running as a service

For always-on operation (channel bots, cron jobs, background tasks):

```bash
junction service install    # systemd on Linux, launchd on macOS
junction service status
junction service uninstall
```

On Linux this writes `/etc/systemd/system/junction.service` (sudo is prompted
for the unit file and the `systemctl` calls; the gateway itself runs as your own
user, never under sudo). When you are already root — a minimal container or
`root` login — no `sudo` binary is required. On macOS it writes a launchd plist
and needs no sudo.

The gateway runs untrusted agent tools, so it must run as a **non-root** user:
the installer sets `User=` to the account behind `sudo` (`$SUDO_USER`, else
`$USER`), and **refuses to install a `User=root` service**. From a bare `root`
login (or `sudo` with no `$SUDO_USER`), first create or pick a normal account and
install as it, e.g. `sudo -u <user> JUNCTION_KIRO_BIN=... junction service
install` (the official Docker image already runs as the `junction` user).

### Setting the service port

A system service inherits none of your shell environment, so `export
JUNCTION_PORT=…` in your shell does **not** reach it. Set the port when you
install so it is baked into the unit:

```bash
JUNCTION_PORT=5477 junction service install
```

To change it later without reinstalling, edit the overrides file the installer
creates and restart:

```bash
sudo sed -i 's/^#\?JUNCTION_PORT=.*/JUNCTION_PORT=5477/' /etc/junction/junction.env
sudo systemctl restart junction
```

`/etc/junction/junction.env` is read by the unit via `EnvironmentFile=`, so its
values override the install-time snapshot and survive a reinstall. Use this to
move the service off the default `5476` when that port is already taken (for
example by a second Junction you also run on this host — there is one
`junction.service` unit, so re-running `service install` updates it in place
rather than creating a second service).

**The `EnvironmentFile=` directive only exists in units written by v0.2.0 or
later.** Upgrading the package never rewrites an already-installed unit, so a
unit installed by an older release (v0.1.3 and earlier) silently ignores
`/etc/junction/junction.env` — editing it changes nothing. Check which kind you
have:

```bash
grep EnvironmentFile /etc/systemd/system/junction.service
```

No output means the directive is missing. Either re-run `junction service
install` (it rewrites the unit in place, keeping the same service), or set
variables with a [systemd drop-in](#setting-other-environment-variables-systemd-drop-in),
which works on any unit version.

### Setting other environment variables (systemd drop-in)

For variables the seeded overrides file does not cover — proxy settings are the
common case — use a systemd drop-in. Drop-ins are systemd's own override
mechanism: they apply to the unit no matter which release wrote it, and they
survive reinstalls, `service install` re-runs, and even
`junction service uninstall` (which removes the unit but never touches
`/etc/systemd/system/junction.service.d/`).

```bash
sudo mkdir -p /etc/systemd/system/junction.service.d
sudo tee /etc/systemd/system/junction.service.d/proxy.conf > /dev/null <<'EOF'
[Service]
Environment="HTTPS_PROXY=http://proxy.example.com:3128"
Environment="HTTP_PROXY=http://proxy.example.com:3128"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart junction
```

A new or edited drop-in is not picked up until `systemctl daemon-reload` runs —
restarting alone is not enough. Verify what the unit resolved to with
`systemctl cat junction` (drop-ins are printed below the unit) or
`systemctl show junction --property=Environment`.

For remote hosts, see [remote-and-mobile.md](remote-and-mobile.md).

## Linux: the agent sandbox and unprivileged user namespaces

On Linux, Junction isolates the agent by entering a **user namespace** and then
a **mount namespace**, over-mounting credential paths such as `~/.aws` and
`~/.ssh` so the agent cannot read them. If that sandbox cannot be built,
Junction **refuses to run the agent** rather than run it unisolated: spawns fail
closed. This is deliberate and is not something to work around casually.

**Ubuntu 23.10 and newer ship `kernel.apparmor_restrict_unprivileged_userns=1`**,
which moves any process that creates a user namespace into a restricted AppArmor
profile with no `CAP_SYS_ADMIN`. The first `unshare` succeeds, the second fails
with `EPERM`, and you see:

```
sandbox: unshare(NEWNS) failed: errno 1
```

### The remedy: let `service install` add an AppArmor profile

```bash
junction service install
```

Where, and only where, this mechanism is the one in play, the installer also
writes `/etc/apparmor.d/junction-userns` and loads it. The profile grants
exactly one permission (`userns`) and is applied by systemd to the junction
service only, via `AppArmorProfile=-junction-userns` in the unit. It is a
**named** profile with no attachment path, so it cannot apply to any other
process, and it is the same approach stock Ubuntu already uses for `chrome` and
`brave`.

This uses the sudo prompt `service install` already needs for the unit file, so
it costs no additional privilege, and it **cannot fail your install**: if the
profile cannot be written, loaded, or verified, you get a warning and the
install continues. `junction service uninstall` unloads and removes it, so a
host is left as it was found rather than carrying an orphaned userns permission.

The installer skips the profile silently, with a reason it can print, when
AppArmor is not an active LSM, when the sysctl is not `1`, when
`apparmor_parser` is absent, or when the parser is older than 4.x (the `userns`
rule needs 4.x or newer). So on Debian, Arch, RHEL and Amazon Linux nothing
changes.

**Running the gateway outside systemd** (for example `junction up` in a
terminal) does not pick up the profile, because systemd is what applies it —
and there is no unprivileged way to enter it yourself. `aa_change_onexec()` into
a named profile is not permitted for an ordinary unconfined user, and `aa-exec`
does **not** fail when it cannot transition: it execs the command unconfined, so
`aa-exec -p junction-userns -- junction up` appears to work and changes
nothing. Run the gateway as the service instead.

### The AppImage (desktop app) needs its own profile

A **`.deb` or `.rpm` install needs none of this section**: the package's
post-install step writes and loads a `userns` profile attached to its own fixed
path under `/opt`, so the sandbox works on a stock Ubuntu 23.10+ host with no
manual step and nothing to re-point later. That fixed path is the whole
difference — everything below exists because an AppImage does not have one.

The profile above is applied **by systemd**, so it covers the installed service
and nothing else. Launching the AppImage directly gives systemd no part to play:
the app execs the bundled backend itself, so neither process gets a profile and
agent spawns fail closed exactly as before. Attach a profile to the AppImage
instead:

```bash
junction sandbox install-profile --path ~/Applications/junction.AppImage
```

**If you only ever downloaded the AppImage, you have no `junction` on your
PATH** — the CLI is bundled inside the app, which is the whole point of that
download. Use the bundled copy instead. The sandbox error message in the app
prints the exact absolute path for you; it looks like this, and it is valid while
the app is running:

```bash
'/tmp/.mount_XXXXXX/resources/backend-dist/junction-backend/bin/junction' \
  sandbox install-profile --path ~/Applications/junction.AppImage
```

Do **not** prefix that with `sudo`. The command elevates only the three steps
that need it (`install`, `apparmor_parser`, `aa-exec`) and prompts you for a
password when it does; running the whole thing as root would execute application
code with privilege for no reason.

Then restart the app. To check whether the launch you are looking at is covered:

```bash
junction sandbox status
```

This writes `/etc/apparmor.d/junction-launcher`, granting the same single
`userns` permission — but **attached** to that executable path, which is how the
kernel can apply it at exec time with no cooperation from the process. The
backend the app spawns inherits it. It is the same mechanism stock Ubuntu uses
for `/etc/apparmor.d/chrome`, `brave`, `1password` and `Discord`.
`junction sandbox remove-profile` unloads and removes it.

Three things the command refuses to do, because an attachment is a permission
grant keyed on a path:

- **A path you do not own.** An AppImage you downloaded is owned by you, which is
  the case this serves. A root-owned binary in a system location is shared with
  every user of the machine, so attaching there would hand the grant to all of
  them - and no blocklist of shared runtimes can be complete (`java`, `mono`,
  `dotnet`, `php`, `wine` and friends are all in the same position as
  `/usr/bin/python3`). If you need to confine a system-wide install, ship a
  packaged profile the way the distro does for `chrome` and `brave`.
- **A world-writable location** (`/tmp`, `/var/tmp`, `/dev/shm`, `/run`, or any
  directory in the path whose permissions let others write). Anyone with a local
  account could put their own file at that path and inherit the grant. Keep the
  AppImage somewhere durable such as `~/Applications`. This also rules out the
  AppImage's own `/tmp/.mount_XXXXXX` runtime directory, which is a fresh random
  path on every launch and could never match twice.
- **A shared interpreter** such as `/usr/bin/python3`. That would grant
  unprivileged user namespaces to every program on the host that runs it.

Because the profile is attached to a path, **moving or renaming the AppImage
silently stops it applying** — the kernel reports no error, the profile just
never matches. `junction sandbox status` detects that and names the stale path;
re-running `install-profile` re-points it. Replacing the file in place (an
in-place update) keeps working, since the path is unchanged.

**Running the gateway in a terminal** (`junction up`) is not covered by
either profile. Use `junction service install` and let systemd run it. There is
no correct profile to attach for a foreground run: the only executable involved
is a shared Python interpreter, and attaching there would hand unprivileged user
namespaces to every Python process on the machine.

> Earlier versions of this page suggested `aa-exec -p junction-userns -- junction
> gateway`. That does not work and has been removed. Entering a **named** profile
> requires `aa_change_onexec`, which an unprivileged unconfined process is not
> permitted to do, and `aa-exec` does not fail loudly when it cannot transition —
> it execs the command unconfined, so the gateway appears to start under the
> profile while running without it. Running it under `sudo aa-exec` does
> transition, but then the gateway runs as root.

**Please do not "fix" this by setting the sysctl to 0.** That disables a
kernel-wide protection for every application on the machine to satisfy one
app-scoped need. The per-application profile exists precisely so you do not
have to.

### Other reasons user namespaces can be denied

The AppArmor profile addresses only the Ubuntu restriction. These are different
mechanisms with different remedies, and they report different errnos. The
sandbox probe names the failing step so you can tell them apart:

| Symptom | Mechanism | Remedy |
|---|---|---|
| `unshare(CLONE_NEWNS)` fails `EPERM`, sysctl is `1` | Ubuntu >= 23.10 AppArmor userns restriction | `junction service install`, or `junction sandbox install-profile` for the AppImage (this page) |
| `unshare(CLONE_NEWUSER)` fails `ENOSPC` / `EUSERS` | `user.max_user_namespaces=0` (CIS-hardened host) | Raise that sysctl |
| `unshare` fails and `kernel.unprivileged_userns_clone=0` | Debian-family legacy knob (defaults to 1 since Debian 11) | Set it to 1 |
| `unshare` fails `EINVAL` / `ENOSYS` | Kernel built without `CONFIG_USER_NS` | None short of a different kernel |
| Fails inside Docker/Podman | The container's seccomp filter denies `unshare` | Container run flags, **not** host config |
| RHEL/Fedora/Rocky/AL2023 | SELinux, not AppArmor | userns is enabled there; the profile is inert |

To see which step is failing on your host:

```bash
python3 -c "
import junction.sandbox as sb
sb.reset_backend(); print(sb.detect_backend(), sb._last_unshare_failure)"
```

`junction doctor` reports the same verdict without the one-liner, and the
dashboard's **Sandbox unavailable** screen names the mechanism and the command
for it directly — the probe classifies the failing step into one of
`apparmor_userns`, `max_user_namespaces`, `userns_denied` or `no_user_ns`, which
is the row of the table above that applies to you.

## Troubleshooting

Always start with `junction doctor`.

### `AcpTimeoutError: ACP prompt timed out`

The `kiro-cli` backend did not answer in time. Five common causes:

1. **`kiro-cli` is not installed.** The gateway raises
   `kiro-cli not found in PATH`. Install it, or use the dashboard's
   **Dock an agent** page.
2. **Not logged in.** Run `kiro-cli login`. An expired session normally
   surfaces as the distinct, non-retryable "kiro-cli is not logged in" error
   rather than a timeout, so check this even when the message differs.
3. **A broken or stale MCP config.** Rebuild it with
   `junction setup --agent-only --clean`. A single unreachable MCP server can
   consume the whole initialization window.
4. **First launch is genuinely slow.** MCP servers can be slow to initialize,
   so the handshake allows up to 4 minutes before giving up. Later timeouts have
   their own watchdogs: a turn that streams text and then goes quiet for 90
   seconds is treated as finished, and a dispatched tool that returns nothing at
   all for 10 minutes is treated as a dead stall and the agent is killed to
   recover the slot.
5. **The host needs a proxy and the service does not have one.** On a
   corporate network, `kiro-cli` must reach its backend through your proxy. A
   systemd service inherits none of your shell's `HTTPS_PROXY`/`HTTP_PROXY`
   exports, so a gateway that works when run from your terminal can still time
   out as a service. Set the proxy variables on the unit with a
   [systemd drop-in](#setting-other-environment-variables-systemd-drop-in),
   then `sudo systemctl daemon-reload && sudo systemctl restart junction`.
   Agent sessions inherit the service environment, so this fixes them. One
   known gap: the first-run setup gate's login probe currently filters proxy
   variables out even when the unit carries them, so it can stay stuck on
   the dock-an-agent page on a proxied host.

### Memory or knowledge search returns nothing

The embedding model is probably still downloading. Check the **Vector Memory**
section of `junction doctor`, which reports the model state and whether the
model URL is reachable, and look for the GGUF under `~/.junction/models/`.
Search falls back to keyword matching until the model lands, then switches over
on its own with no restart. For an airgapped or firewalled host, point
`JUNCTION_EMBED_MODEL_URL` at a mirror; the sha256 pin still verifies the file.

### The gateway will not start

```bash
junction doctor
junction up --port auto   # bind an OS-assigned port if 5476 is taken
```

## Uninstalling

Uninstalling removes the Junction binary and its runtime but **preserves your
data home** (`~/.junction`) — configuration, credentials, memory, sessions,
apps, and the audit chain remain intact. This is intentional: reinstalling picks
up where you left off without re-running setup or losing history.

Before uninstalling, stop any running gateway and remove the system service if
one is installed:

```bash
junction stop                # stop a running foreground gateway
junction service uninstall   # removes the systemd unit / launchd plist
```

Then follow the section matching your install method.

### pipx leftover

If an older `cli.sh` path used `pipx`:

```bash
pipx uninstall junction
```

### Managed venv leftover

If an older `cli.sh` path created a managed venv and a symlink.
Remove both:

```bash
rm -f ~/.local/bin/junction
rm -rf "${JUNCTION_VENV:-${JUNCTION_HOME:-$HOME/.junction}-venv}"
```

If you set `JUNCTION_VENV` to a custom path, verify its contents before
removing it — `cli.sh` overlays that directory with venv files, and an `rm -rf`
on a path you already used for something else will take that too.

### pip / pip wheel install

```bash
pip uninstall junction
```

If installed in a dedicated virtualenv:

```bash
rm -rf /path/to/your/venv
```

### From source (development)

Remove the editable install and the build artifacts:

```bash
# Chained so a failed `cd` (wrong path) can never run `rm -rf` in your current directory:
cd /path/to/junction \
  && pip uninstall junction \
  && rm -rf .venv build dist   # editable install, local venv, and build outputs
```

### macOS desktop app (DMG / zip)

1. Quit Junction from the menu bar or Dock.
2. Drag **Junction.app** from `/Applications` to the Trash (or `rm -rf`).

There is no installer package or receipt to clean — the DMG is a drag-install.

### Linux AppImage

Delete the AppImage file wherever you placed it:

```bash
rm -f ~/Applications/Junction-x86_64.AppImage   # or wherever you saved it
```

### Windows (NSIS installer)

Use **Settings → Apps → Installed apps**, find "Junction", and click
**Uninstall**. The NSIS uninstaller removes the application directory and
shortcuts but does not touch `~/.junction`.

### Docker

```bash
docker stop junction && docker rm junction   # graceful stop, then remove
docker rmi ghcr.io/laqaer/junction:stable # remove the image (match the tag you pulled)
```

`docker stop` sends SIGTERM and gives the gateway time to run its shutdown
flush; `docker rm -f` sends SIGKILL immediately, which can drop up to one
5-second flush interval of recent session state.

## Removing user data

Uninstalling via any method above leaves your data home intact. To also remove
all user data:

```bash
# Back up first — this is irreversible. `junction snapshot` only captures
# memory/config/skills/workspace, not `.env`, credentials, or installed apps,
# so a full copy of the data home is the only complete backup. Chained with
# `&&` so a failed copy (e.g. disk full) blocks the delete rather than racing
# ahead of it. Point the copy at a location you control OUTSIDE the data home:
cp -a "${JUNCTION_HOME:-$HOME/.junction}" ~/junction-backup \
  && rm -rf "${JUNCTION_HOME:-$HOME/.junction}"
```

The backup is a full copy of your credentials (`.env`), signing keys, and
session data, and it does NOT inherit the agent's path protections that guard
the live data home — store it somewhere the agent cannot reach and delete it
once the reinstall is confirmed good.

This deletes configuration, credentials (`.env`), session history, memory
databases, installed apps, and the embedding model cache.

> **Docker:** the commands above target a host data home. A Docker install keeps
> everything in the `junction-home` named volume instead, so remove that rather
> than `~/.junction`: `docker volume rm junction-home` (or `docker compose down -v`).

> **Note:** App Kit data is preserved per-app by default. To remove an
> individual app's data before or instead of purging the whole home:
> `junction app uninstall NAME --purge-data`

## Clean reinstall

A clean reinstall removes both the binary and the data home, then installs
fresh. Use this when `junction doctor` reports issues that setup cannot fix,
or when you want a completely fresh start.

```bash
# 1. Stop any running gateway, then remove the service
junction stop                        # stop a foreground gateway (service uninstall won't)
junction service uninstall 2>/dev/null

# 2. Uninstall the binary (use the matching command from above)
pipx uninstall junction          # or: pip uninstall junction, rm the AppImage, etc.

# 3. Back up and remove the data home (chained so a failed copy blocks the delete)
cp -a "${JUNCTION_HOME:-$HOME/.junction}" ~/junction-backup \
  && rm -rf "${JUNCTION_HOME:-$HOME/.junction}"

# 4. Reinstall from source (Junction has no public curl|sh CDN)
git clone https://github.com/laqaer/junction.git && cd junction
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 5. Run first-time setup
junction setup
junction doctor
```

Replace step 4 with your preferred install method (pip wheel, source build,
desktop app) as described in the [Install paths](#install-paths) section above.

## Data retention details

For reference, the data home structure and what each uninstall path touches:

- `junction service uninstall` removes only the systemd unit (plus the AppArmor
  profile it installed) or the launchd plist.
- Python and npm package removal has no `preuninstall` or `postuninstall`
  cleanup hook.
- The macOS DMG/zip and the Linux AppImage have no cleanup hook, so removing the
  application bundle or image leaves the data home intact.
- A Linux `.deb` / `.rpm` removal DOES run the package's own post-remove step,
  which drops `/usr/bin/junction-desktop` and the installed AppArmor profile. It
  deliberately leaves the data home alone: `~/.junction` holds your sessions,
  memory and credentials, so it is yours to remove (see
  [Removing user data](#removing-user-data)), not the package manager's.
- App Kit uninstall preserves `apps/<name>/data/` by default. Deleting that app
  data is a separate, explicit action:
  `junction app uninstall NAME --purge-data`, or unchecking **Keep app data** in
  the confirmation dialog.

**Windows NSIS uninstaller behavior.** `nsis.oneClick` is false and
`nsis.deleteAppDataOnUninstall` is left false, so the uninstaller removes only
the application install directory and its shortcuts. It never removes the data
home. Each signed Windows installer must pass an install,
create-sentinel-under-`~/.junction`, uninstall, verify-sentinel smoke test
before release.

## Next steps

- [Slack setup](slack-setup.md): create and configure the Slack app.
- Other channels: [Discord](../../src/junction/docs/discord-integration.md),
  [Telegram](../../src/junction/docs/telegram-integration.md),
  [Teams](../../src/junction/docs/teams-integration.md),
  [Webex](../../src/junction/docs/webex-integration.md),
  [WeCom](../../src/junction/docs/wecom-integration.md),
  [WeChat](../../src/junction/docs/weixin-integration.md), and
  [WhatsApp](../../src/junction/docs/whatsapp-integration.md).
- [Remote and mobile access](remote-and-mobile.md): 24/7 operation on a remote
  host, and reaching the dashboard from a phone.
- [Architecture overview](../architecture/overview.md): system diagrams and the
  component map.
- [Security deep dive](../architecture/security-deep-dive.md): sandbox,
  governance, and denied commands.
- [App Kit guide](../app-kit/getting-started.md): build apps that extend
  Junction.
- [CONTRIBUTING.md](../../CONTRIBUTING.md): development setup and the PR
  workflow.
