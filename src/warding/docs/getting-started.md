# Getting Started with Warding

Warding is a local control plane: dock ACP coding agents and route their
models. Chat from the web dashboard, the CLI, or a messaging channel.
A vendor agent CLI is optional.

## Prerequisites

| Requirement | Needed for | Floor |
|-------------|------------|-------|
| **Python** + pip | Backend | `>= 3.10` |
| **Node.js** + npm | Building the dashboard from source | `>= 22` (24 LTS recommended) |
| An ACP runtime | Driving the LLM | Cursor, Claude, Codex, Grok, … — a vendor agent CLI is optional |

Node is only needed to *build* the dashboard. A source install that already
has `website/dist` staged does not need Node at runtime.

**Platforms: macOS, Linux, and Windows.** Windows runs natively from a Python
source install and is launched as `python -m warding up` or `warding up`.

## Installation

On macOS and Linux, one command installs from this repository. It needs
Python 3.10+ and Node.js 22+ so the dashboard is built. Read
`scripts/get-warding.sh` before you run it. It does not start the server.

```bash
curl -fsSL https://raw.githubusercontent.com/myrmitis/warding/main/scripts/get-warding.sh | sh
warding setup
warding doctor --quick
warding up
```

A source checkout is the path when you are changing Warding:

```bash
git clone https://github.com/myrmitis/warding.git
cd warding
python3 -m venv .venv && source .venv/bin/activate
cd website && npm install && npm run build && cd ..
pip install -e ".[dev]"
warding setup
warding doctor --quick
warding up
```

The dashboard has to be built before the backend install, because the built
`website/dist` is staged into the package and served by the gateway. `make
build` does both steps plus a `.venv`.

The dashboard is `http://localhost:5476`.

`warding up` starts a loopback model catalog. It serves health and the
catalog only. `warding planes` shows both rails, `warding router catalog`
lists namespaced model choices, and `warding router plan` shows the
orchestration → planning → execution DAG. The docked agent uses models it
already serves. A completion posted to the catalog answers 501. Never paste
provider keys into chat. If the catalog listener is down, the gateway still
runs. The passing first-run transcript is in the install guide under
"What a successful test looks like".

### Agent backend (vendor CLI optional)

`agent.provider` is `acp`. `agent.acp_backend` defaults to `auto`: Warding
docks the first installed of Cursor, Claude, Codex, Kimi, DeepSeek Harness,
Goose, Grok, Pi, Droid. A named vendor CLI remains selectable and last in
that list. Install one only when you want that harness. Warding does not
sign you into a vendor account.

## First-Time Setup

```bash
warding setup
warding doctor --quick
warding up
```

`warding gateway` is the same server as `warding up` and remains for scripts.

Connect Slack, Discord, or other channels later from the dashboard
(Settings → Channels).

## Docs

Site: https://warding.dev

Source: https://github.com/myrmitis/warding
