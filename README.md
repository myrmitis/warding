<p align="center">
  <img src="assets/banner.svg" alt="Warding. The lamp stays on. The rules stay shut." width="100%">
</p>

**Warding runs the coding agent you already pay for, all night, on your own
box, and can ask you in chat before it acts when you enable approvals —
under a policy it cannot read or rewrite.**

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-656d76?style=flat-square" alt="Apache 2.0 license"></a>
  <a href="https://warding.dev"><img src="https://img.shields.io/badge/Site-warding.dev-B3301A?style=flat-square" alt="Warding site"></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/Docs-1A1814?style=flat-square" alt="Documentation"></a>
  <a href="SECURITY.md"><img src="https://img.shields.io/badge/Security%20policy-2E6B45?style=flat-square" alt="Security policy"></a>
</p>

[Quickstart](#quickstart) ·
[What it does](#what-it-does) ·
[The rules it can't open](#the-rules-it-cant-open) ·
[What we don't claim](#what-we-dont-claim) ·
[Agent Worlds](#agent-worlds) ·
[Pricing](#pricing) ·
[Contributing](#contributing)

## Quickstart

Warding is a **source-only local beta**: it builds and runs on one machine you
control, from a checkout of this repository. This is a preview of `main`, not
a released version — check the
[open pull requests](https://github.com/myrmitis/warding/pulls) before assuming
a reported fix is included — and this exact tree has not been verified by a
clean-machine install. Everything assumes one operator on one machine:
`localhost` is your own computer, `~/.warding` is yours alone, and you install
and sign in to the agent harness yourself. There is no account with us and no
shared multi-tenant server.

You need macOS or Linux, Python 3.10+, Node.js 22+ with npm (the dashboard is
built from source), git, and one coding-agent CLI on your `PATH`, signed in the
way its vendor expects: `claude`, `codex`, `goose`, `cursor`, `kimi`, `grok`,
`opencode`, `pi`, `droid` or `kiro-cli`. For Claude Code, the ACP project's
`claude-agent-acp` adapter is fetched with `npx` on first run. Windows follows
the [Windows guide](docs/guides/windows-install.md).

```bash
git clone https://github.com/myrmitis/warding.git
cd warding
bash minimal_install.sh   # builds into ./.venv, links warding into ~/.local/bin
source .venv/bin/activate
warding setup             # first-run config; the data home is ~/.warding
warding up                # model catalog + dashboard, in the foreground
```

Activating the virtual environment makes `warding` available even when
`~/.local/bin` is not on your `PATH`.

`warding up` docks the agent, serves the dashboard on loopback at
`http://localhost:5476`, and keeps running in that terminal. The dashboard asks
for authentication even on loopback, so open it with a link minted from a
second terminal:

```bash
cd /path/to/warding      # your checkout directory
source .venv/bin/activate
warding token --port 5476
```

That prints a signed, short-lived URL for this gateway; open it in a browser on
this machine within about five minutes. Treat it as a credential: do not paste
it into chat, issues or shared notes, and do not commit it.

**Chat needs an agent you are signed in to.** Warding is not a model: a chat
turn runs through an installed ACP harness that you have already logged in to.
`agent.acp_backend` is `auto`, which docks the first *installed* harness in
the preference order (Cursor, Claude Code, Codex, and so on), not the first one
on `PATH`. To choose one — Codex, say — install the
[Codex CLI](https://github.com/openai/codex#quickstart) and sign in with your
own account, then pick it in the dashboard under **Settings ▸ Agents & plans ▸
Chat harness** (it applies to new chats; no restart), or run
`warding config set agent.acp_backend codex`
([install guide](docs/guides/install.md)). `warding planes` shows what is
docked. kiro-cli is not required.

This is version 0.5.0 from source. There is no tagged release, wheel,
Docker image or signed desktop build published yet; the source install above
is the supported path, and the browser dashboard is the supported local
surface. [`scripts/get-warding.sh`](scripts/get-warding.sh) runs the same
source build from one command: it clones or fast-forwards a checkout, then runs
`minimal_install.sh` (it tracks the default branch and does not start the
server; read it before you run it). To keep it running after you close the
terminal, `warding service install` registers a systemd unit or a launchd
agent ([install guide](docs/guides/install.md)).

**Beta status and known limitations.** This is pre-release software built from
`main`, not a pinned beta release. Expect rough edges, keep `~/.warding`
backed up, and check the open pull requests before assuming a fix is present.
Windows has documented feature limits
([Windows guide](docs/guides/windows-install.md)), and remote or multi-user
deployments are outside this beta.

## What it does

| | What you get |
|---|---|
| **Chat** | Talk to the docked agent from the web dashboard, the CLI (`warding chat`), or one of ten chat apps. Sessions persist and resume after a restart. |
| **Schedules** | Cron jobs with a template gallery: nightly dependency checks, morning digests, weekly reports. They run on your hardware. No run cap from us; your model plan's limits still apply. |
| **Walk-away tasks** | `warding run TASK.md` plans, executes, validates, retries, and resumes from checkpoints. |
| **Subagents** | Fan work out to isolated background agents from the dashboard or CLI, and from chat on kiro-cli. The harness router can send each one to another installed harness. |
| **Approvals** | A gated tool call arrives as Approve / Deny buttons in Slack, Telegram, Discord, Microsoft Teams and Webex, and as a typed reply on WhatsApp. Opt-in: the default approval mode is Auto, so set `agent.approval_mode: interactive` (or pick Interactive in the dashboard) for calls to wait for you. Built-in deny rules never ask. |
| **Memory, lessons, skills** | Preferences and project context persist across sessions; corrections become lessons; repeated patterns become skills you can inspect or drop. |
| **Agent Worlds** | Seven pixel-art scenes where every live session is an animated character. |
| **The desk** | 21 built-in apps, 18 themes, 12 dashboard languages, a model catalog that lists names. |

### The harness you choose, and where subagents go

Warding launches the official CLI you already use, under your own login, and
speaks the Agent Client Protocol to it. Your chat sessions run the one harness
you choose in one setting; your schedules, memory and channels stay when you
switch. Spawned subagents can be routed to another installed harness by the
harness router: flat-rate plan quota before metered spend, the kind of task,
and a cooldown after a usage limit or a failed login. It picks a harness and
never forwards provider traffic; each harness runs under its own login.
`warding route` shows the lanes and what each kind of work would get. Warding
Labs never sees your tokens or keys: there is no server of ours in the loop.

"Verified" below means someone ran that cell on this tree and recorded the
result. Nothing else is implied.

| Harness | Chat | Schedules | Channels | Approvals | Overnight |
|---|---|---|---|---|---|
| `kiro-cli` | first-class harness, unverified here | first-class harness, unverified here | first-class harness, unverified here | first-class harness, unverified here | unverified |
| Claude Code (`claude`, via the ACP project's `claude-agent-acp` adapter, fetched with `npx` on first run) | verified | unverified | unverified | unverified | unverified |
| Codex, Cursor, Goose, Kimi, DeepSeek Harness, Grok, OpenCode, Pi, Droid | registered, unverified | registered, unverified | registered, unverified | registered, unverified | unverified |

The harness router is registered and covered by unit tests; no routed run has
been verified at runtime yet. No Gemini is docked. The list of registered
harnesses is `src/warding/acp/runtimes.py`.

### Ten chat apps, labelled

| In-chat approvals | Apps |
|---|---|
| Approve / Deny buttons | Slack, Telegram, Discord, Microsoft Teams, Webex |
| Typed reply | WhatsApp |
| Chat only, no in-chat approvals yet | iMessage, WeChat, WeCom, Feishu |

Setup guides: [Slack](docs/guides/slack-setup.md),
[Telegram](src/warding/docs/telegram-integration.md),
[Discord](src/warding/docs/discord-integration.md),
[Teams](src/warding/docs/teams-integration.md),
[Webex](src/warding/docs/webex-integration.md),
[WhatsApp](src/warding/docs/whatsapp-integration.md),
[WeCom](src/warding/docs/wecom-integration.md),
[WeChat](src/warding/docs/weixin-integration.md).

## The rules it can't open

**Article 1. The agent cannot read or write its own policy.** The policy file,
the profiles, the admission policy and the computer-use switch under the data
home sit on the same sensitive-path list as `~/.ssh`, `~/.aws` and `~/.gnupg`.
Read, write and extract verbs against those paths are refused at Warding's own
PreToolUse gate and, where a backend exists, by the OS sandbox's bind rules.
The agent cannot loosen a ceiling it cannot open.

**Article 2. Secrets are redacted before they reach the log.** Credential
shapes — AWS access keys, private keys and the like — are redacted at one
chokepoint before tool output reaches a chat surface or the audit log. This is
always on; there is no policy key that turns it off.

**Article 3. Tool decisions are appended to a hash-chained audit log you can
verify.** Every gate decision lands in `security_events.jsonl` as an entry
signed into an HMAC-SHA256 chain, with the key kept outside the log directory.
`warding security verify` checks the chain; `warding security events` and
`audit` read it.

**Article 4. Anything not granted by both the policy and the profile is
denied.** The effective permission for a tool or MCP call is the intersection
of the policy and the active profile, tightest wins, enforced at Warding's own
gate even when the agent's own config granted the tool.

What is enforced where: the gate is fail-closed for denied paths and commands
and fail-open for tools the harness pre-authorised; computer-use refusals run
in band on the dispatch path, never at the hook; the OS sandbox fails closed
where no backend exists unless you opt in. Unaudited by a third party. The full
model, with threat boundaries, is in the
[security deep dive](docs/architecture/security-deep-dive.md); how to report a
bypass is in [SECURITY.md](SECURITY.md).

## What we don't claim

- Chat sessions run the one harness you choose. Routing a spawned subagent to
  another installed harness is registered and unit-tested, not verified at
  runtime; the router picks a harness and forwards no provider traffic.
- The model catalog lists names; it forwards nothing and holds no keys.
- Approve buttons on five chat apps; WhatsApp is typed; four apps are chat-only.
- Cron and subagents *from chat*, and the agent's mid-turn questions, work on
  kiro-cli today; on other harnesses create jobs and spawn subagents from the
  dashboard or CLI, and the agent cannot ask you a question mid-turn.
- The OS sandbox fails closed — it refuses to run rather than run unconfined —
  on Windows, in containers without user namespaces, and on Ubuntu ≥ 23.10
  until `sudo warding sandbox install`; you can opt in to unsandboxed execution
  with a loud warning.
- Unaudited by a third party. Single owner. No hosted service. No signed
  installers yet.
- Your vendor's terms and any future metering of unattended use apply and may
  change.
- The default build contacts no server of ours; the embedding model is
  downloaded from a third-party CDN on first embedding use.
- No overnight run has been verified on any harness yet.

## Agent Worlds

Every live session gets a pixel-art character. Seven scenes ship: an office,
a panda office, an underwater lab, a watering hole, a wizard tower, a neural
constellation and a mission-control floor. Sessions type, pause for an
approval, and go idle in view; the scene follows the theme you pick. Works
with whichever harness is docked. Wallpaper export of the live scene is in
development.

## Pricing

Everything in this repository is free, Apache-2.0, and nothing in the tree is
gated. The paid items, each labelled as available, pre-order or waitlist, are
on the [pricing page](https://warding.dev/pricing/): a Founding Supporter
tier with real digital goods, a paid setup session on your own machine, and
free waitlists for a Team companion and a hosted late desk.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the dev loop, then
[AGENTS.md](AGENTS.md) for the rules an AI assistant follows in this tree.
Bugs and feature requests go to
[GitHub Issues](https://github.com/myrmitis/warding/issues). Vulnerabilities
go through [SECURITY.md](SECURITY.md), never a public issue.

```bash
pip install -e ".[voice]" --group dev && pytest      # backend
cd website && npm ci && npm run check && npm run build   # dashboard
```

Contributors can build the same checkout with the Makefile instead of
`minimal_install.sh`, with the same prerequisites: `make build` provisions
`./.venv` and builds the dashboard, and `warding doctor --quick` verifies the
install. Then follow the Quickstart from `warding setup`.

| Topic | Start here |
|---|---|
| Install and operate | [Install guide](docs/guides/install.md), [Windows](docs/guides/windows-install.md), [Remote host](docs/guides/remote-and-mobile.md) |
| Features | [User docs](src/warding/docs/index.md), [Cron](src/warding/docs/cron-and-scheduling.md), [Task runner](src/warding/docs/task-runner.md), [Memory](src/warding/docs/memory-and-learning.md) |
| Architecture | [System overview](docs/architecture/overview.md), [Security deep dive](docs/architecture/security-deep-dive.md), [MCP](docs/architecture/mcp.md), [App Kit](docs/app-kit/getting-started.md), [Decision records](docs/adr/README.md) |
| Project | [Product](PRODUCT.md), [Roadmap](ROADMAP.md), [Tenets](TENETS.md), [Governance](GOVERNANCE.md), [Maintainers](MAINTAINERS.md), [Changelog](CHANGELOG.md) |

## Security

Report a vulnerability or a policy bypass privately through the
[GitHub advisory form](https://github.com/myrmitis/warding/security/advisories/new).
Reports are acknowledged within five business days. Scope, the bypass-report
policy and what is out of scope are in [SECURITY.md](SECURITY.md).

## Contributors

Warding credits authors of pull requests merged in this repository. The
[contributors graph](https://github.com/myrmitis/warding/graphs/contributors)
is the live list as the project grows.

<a href="https://github.com/laqaer" title="laqaer"><img src="https://github.com/laqaer.png?size=64" width="64" height="64" alt="laqaer" /></a>

If you contributed and would like to be added, corrected, or removed, please
open an issue or a pull request.

## License

Warding is licensed under the [Apache License 2.0](LICENSE). See
[NOTICE](NOTICE) for attribution.
