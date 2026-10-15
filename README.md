<p align="center">
  <img src="assets/banner.svg" alt="Warding. The lamp stays on. The rules stay shut." width="100%">
</p>

**Product goal (in development):**

> Warding runs the coding agent you already pay for, all night, on your own
> box, and can ask you in chat before it acts when you enable approvals —
> under a policy it cannot read or rewrite.

Today the local beta runs installed agents under their own CLI logins, with a
dashboard, task delegation and opt-in tool approvals. Overnight work is
unverified. The policy ceiling uses Warding's permission gate and OS sandbox,
unaudited by a third party; native Claude/Codex operations still have a
[policy-protection gap](https://github.com/myrmitis/warding/issues/18).

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

This walkthrough sets up **Codex with your ChatGPT subscription and Claude Code
with your Claude subscription on macOS**. Warding runs on your computer; GitHub
hosts its source and these instructions. Chat uses one chosen harness; delegated
workers can use the other, each under its own login.

Warding 0.5.0 is a **source-only local beta**. The browser dashboard is the
supported local surface; no tagged release, published wheel, Docker image or
signed installer is available yet. Clean-machine installation and live
cross-harness delegation have not been qualified on this tree. Start with a
supervised task in a disposable repository. See
[what still needs qualification](#before-relying-on-unattended-work).

### 1. Prepare macOS and sign in to both agents

You need git, Python 3.10+ (3.12 recommended), and Node.js 22.12+ (24 LTS
recommended) with npm/npx. Node is also used to launch the ACP adapters.
If you use [Homebrew](https://brew.sh), one setup is:

```bash
brew install git python@3.12 node@24
export PATH="$(brew --prefix python@3.12)/bin:$(brew --prefix node@24)/bin:$PATH"
brew install --cask codex claude-code

python3.12 --version
node --version
codex --version
claude --version
```

Existing installations can be used instead. Official installation alternatives:
[Codex CLI](https://github.com/openai/codex#quickstart) and
[Claude Code](https://github.com/anthropics/claude-code#get-started).

Sign in as the **same macOS user who will run Warding**:

```bash
codex login
claude auth login
```

For Codex, choose **Sign in with ChatGPT** using your eligible ChatGPT plan.
For Claude Code, choose your Claude subscription account. API-key/Console billing
is a separate route; check the account and billing method selected in each CLI
if you intend to use subscription allowances. Run `codex` and `claude` once in a
test folder, follow their first-run prompts, and confirm each can answer a simple
message. Then exit each session.

Warding uses those CLI logins and does not pool the subscriptions into one model
account. Each provider's limits, model access and terms still apply. Keep login
tokens and credential files in their CLI-owned stores; no key belongs in a
Warding chat or `routing.json`. The ACP project's Claude/Codex adapters are
resolved through installed adapters or `npx`, so the first launch may download
an adapter even when the official CLI is already installed.

Linux uses the source build below with the official CLI installation steps for
that platform. For Windows, read the [Windows guide](docs/guides/windows-install.md)
first; the filesystem sandbox support differs from macOS/Linux.

### 2. Install Warding and choose the primary chat agent

```bash
git clone https://github.com/myrmitis/warding.git
cd warding
bash minimal_install.sh
source .venv/bin/activate

warding setup
warding config set agent.acp_backend claude
warding config set agent.approval_mode interactive
warding route init
warding doctor
```

The installer builds the dashboard and installs Warding into `./.venv`; it also
links `warding` into `~/.local/bin`. Activating the venv makes the command
available in this shell. Configuration lives under `~/.warding`, or the
`WARDING_HOME` directory you explicitly selected. Keep that choice consistent
between terminals and any later service.

Other installation paths are covered in the
[install guide](docs/guides/install.md), including the
[bootstrap installer](scripts/get-warding.sh).

Here Claude is the primary chat agent. Use `codex` instead of `claude` in the
config command to reverse that choice. The default remains `auto`; selecting an
agent explicitly avoids another installed harness being chosen. Settings →
Agents & plans → Chat harness changes the choice for new chats. Finish active
work before switching; a new chat is the clearest way to check the new choice.

Approvals default to **Auto**. The example opts into **Interactive** for gated
calls. This does not make every native harness operation request permission;
[the Claude/Codex policy-protection gap](https://github.com/myrmitis/warding/issues/18)
remains open. Scope the first task to non-sensitive files and inspect the result.

`warding route init` writes lanes for installed agents and preserves an existing
routing file by refusing to overwrite it. In Settings → Agents & plans, keep the
Claude and Codex lanes enabled and set their billing type to **subscription**
when that matches their actual CLI login. Disable other lanes if you want only
these two used for routed work. Preserve any limits you already configured;
zero/unknown limits are not proof of unlimited provider quota. Model fields can
stay at their inherited defaults; choose explicit models only from the active
harness's advertised options.

In the full `warding doctor` output, check the **Sandbox** section. On macOS,
require `backend: ✅ sandbox-exec` before starting agent work. A skipped/no-backend
message or a probe warning is not success, even if the command exits with zero.
This probes backend availability for the diagnostic process; it does not prove
that every harness operation respects the policy ceiling. `doctor --quick`
only shows the composed inventory, and `sandbox status` checks Linux AppArmor
launcher coverage rather than the Mac backend.

Sandbox availability depends on the macOS version and host configuration.
If the backend is unavailable or cannot be verified, inspect the diagnostic
guidance and [security model](docs/architecture/security-deep-dive.md#layer-0-os-level-sandbox-sandboxpy)
before starting agent work. The
[Linux troubleshooting section](docs/guides/install.md#linux-the-agent-sandbox-and-unprivileged-user-namespaces)
applies only to Linux. The guide does not require enabling unconfined execution.

### 3. Start the dashboard

In this terminal:

```bash
warding up
```

Keep it open. In a **second terminal**, activate this checkout's environment and
mint a private dashboard login link. If you used the Homebrew setup above,
repeat its PATH export in this new shell first so it also sees Node 24:

```bash
export PATH="$(brew --prefix python@3.12)/bin:$(brew --prefix node@24)/bin:$PATH"
cd /path/to/warding
source .venv/bin/activate
warding token --port 5476 --ttl 1h
```

Open the printed URL locally; the dashboard is at `http://localhost:5476`.
The URL is a bearer credential, so keep it out of chat, commits and shared notes.
Continue with the commands below in this second terminal. Both terminals must
see the same CLI executables, user login state and WARDING_HOME.

### 4. Check each subscription through Warding

```bash
warding planes
warding route
warding route check codex claude
warding route run --harness codex "Reply exactly CODEX_OK. Do not use tools."
warding route run --harness claude "Reply exactly CLAUDE_OK. Do not use tools."
```

The generated lane IDs are `codex` and `claude`; existing custom routing may use
different IDs, which `warding route` lists. **Check starts adapters without a
model prompt.** The two real reply commands exercise each selected login/model
and consume its allowance. A successful connection check alone does not prove
that authentication or the selected model works. Resolve failures before
attempting a multi-agent task. Run routed commands in an interactive terminal so
requested tool approvals can be answered.

### 5. Let Codex implement and Claude review

First try a small shared-file workflow in a **new disposable repository** under
`~/workspace`, one of the default allowed roots for delegated work:

```bash
mkdir -p "$HOME/workspace"
warding_demo=$(mktemp -d "$HOME/workspace/warding-demo.XXXXXX")
cd "$warding_demo"
git init
printf '# Warding demo\n' > README.md
git add README.md

warding route run --harness codex --kind implement --cwd "$PWD" \
  "Append exactly one Markdown bullet '- Codex implementation demo' to README.md. Change no other files. Do not commit or push."
git diff -- README.md

warding route run --harness claude --kind review --cwd "$PWD" \
  "Review the README.md working-tree diff. Check that it adds exactly one bullet '- Codex implementation demo'. Report findings. Do not edit files, commit or push."
git diff -- README.md
```

Staging the initial file makes the later edit visible to `git diff` without
requiring a commit. Wait for implementation to finish before starting review.
These commands use fresh agent sessions sharing the same files and diff; they
do not transfer one harness's native conversation to the other. Review-only
wording is a task instruction, not an enforced read-only sandbox. Inspect the
diff and relevant tests yourself before accepting work.

For **agent-managed delegation**, open a new dashboard chat on Claude or Codex.
Current source injects Warding's managed MCP tools into both, when the session
has an identity and the asking-mode pin succeeds. Once both reply checks above
work, adapt this request with the absolute path printed by `pwd`. It uses a
different bullet so you can reuse the disposable repository above:

> Use `spawn_run` with `harness="codex"`, `kind="implement"` and
> `cwd="/absolute/path/to/warding-demo"`. Give it this complete task: "Ensure
> README.md contains exactly one Markdown bullet '- Managed delegation demo'.
> Change no other files. Do not commit or push." Wait for it to finish.
>
> Then use a separate `spawn_run` with `harness="claude"`, `kind="review"`
> and the same absolute `cwd`. Give it this complete task: "Review the README.md
> working-tree diff. Check that '- Managed delegation demo' appears exactly once
> and report any unexpected changes, allowing the earlier '- Codex implementation
> demo' bullet. Report findings. Do not edit files, commit or push."
>
> Return both results and identify which harness actually ran each phase.

Supply the absolute repository path as each worker's `cwd`. Delegated `cwd`
values must be under `agent.subagent_cwd_allowed_roots` (by default
`~/workspace` and `~/workspaces`). If the chat has no `spawn_run` tool or a worker
fails, inspect that failure; the direct terminal workflow above remains useful
for diagnosing the two lanes. This source-supported dashboard flow is still
**unverified with live subscriptions on this tree**.

Later, `harness="route"` lets the router choose a lane by task kind, quota
accounting and cooldown; `warding route pick implement` / `review` explains the
choice without running a task. This differs from task-runner step routing,
which is opt-in through `routing.json`'s `route_tasks` setting. Leave that for
after the bounded handoff works. Details:
[harness router](docs/system-specs/modules/harness-router.md).

### Before relying on unattended work

A usable first milestone is both real reply checks plus one inspectable
Codex-change/Claude-review result on your Mac. That evidence has to come from
your installed versions and accounts; the instructions are not a live
acceptance report. Remaining work before dependable unattended collaboration:

| Need | Existing work |
|---|---|
| Policy protection for native Claude/Codex operations that skip permission requests | [#18](https://github.com/myrmitis/warding/issues/18); includes trusted MCP compatibility and OS enforcement |
| Readiness for the actual model/context, and truthful failures after tool activity | [#40](https://github.com/myrmitis/warding/issues/40), [#15](https://github.com/myrmitis/warding/issues/15) |
| Resume unfinished work with compatible session/harness state and controlled side effects | [#17](https://github.com/myrmitis/warding/issues/17), [#21](https://github.com/myrmitis/warding/issues/21) |
| Shared task/subagent dispatch caps and visible approvals | [#14](https://github.com/myrmitis/warding/issues/14), [#22](https://github.com/myrmitis/warding/issues/22) |

No overnight run is verified on any harness. Keep the first workflow supervised;
service installation and scheduling are later steps in the
[install guide](docs/guides/install.md#running-as-a-service).

## What it does

| | What you get |
|---|---|
| **Chat** | Talk to the docked agent from the web dashboard, the CLI (`warding chat`), or one of ten chat apps. Sessions persist and resume after a restart. |
| **Schedules** | Cron jobs with a template gallery: nightly dependency checks, morning digests, weekly reports. They run on your hardware. No run cap from us; your model plan's limits still apply. |
| **Walk-away tasks** | `warding run TASK.md` plans, executes, validates, retries, and resumes from checkpoints. |
| **Subagents** | Fan work out to isolated background agents from the dashboard or CLI; managed MCP delegation is also registered for Claude Code and Codex, with live verification pending. The harness router can send each one to another installed harness. |
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

**Article 1. Policy paths are protected at Warding's PreToolUse gate.**
The policy file, profiles, admission policy and computer-use switch are sensitive
paths alongside `~/.ssh`, `~/.aws` and `~/.gnupg`; read, write and extract attempts
that reach this gate are refused. Native harness operations do not all reach
it. In particular, process-level policy concealment for Claude Code and Codex
is incomplete ([#18](https://github.com/myrmitis/warding/issues/18)); this beta
does not establish an unreadable/unwritable policy ceiling for those harnesses.

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
- Managed MCP tools are registered for Claude Code and Codex as well as the
  established kiro-cli path; other harnesses have their own capability limits.
  Their availability depends on session identity, adapter support and permission
  mode. Live cross-harness delegation and in-chat approval behavior remain
  unverified here; tool registration alone does not prove a successful run.
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
