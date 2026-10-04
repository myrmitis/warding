# Roadmap

Make every promise true, then prove it in public. No calendar estimates in
this file: milestones are gates, and a gate is green or it is not.

Identity: [`WORKING_BRIEF.md`](WORKING_BRIEF.md). Lane map:
[`docs/TASK_MAP.md`](docs/TASK_MAP.md). Agent loop:
[ADR 0006](docs/adr/0006-agent-os-no-automerge.md).

Work is tracked in three places, with different authority. GitHub issues are
the record of status for bugs, features, and stories; the ADRs
([`docs/adr/`](docs/adr/README.md)) own the *why*; and
[`docs/TASK_MAP.md`](docs/TASK_MAP.md) is a dated local handoff for work in
flight. Local work is real, just unmerged, and "merged" is not "released". The
operator's `~/dev/memory/INDEX.md` is a reference, not authority: a reusable
lesson or convention is proposed as a memory record with its exact source; an
operator merge makes it an accepted reference, and the owning repository always
stays authoritative.

**Already on `main`.** The bootstrap work (contributor docs, the `site/`
overlay, CLI chrome, catalog health, the Vercel preview) and the ship program
are merged. The built-in model catalog is merged: `warding up` binds a loopback listener that
serves `/health` and `/catalog`, completion routes answer `501` with `code`
`model_router_no_forward`, no provider translation is bundled, and a busy
port is left to whatever already owns it. The per-role model and effort keys, OpenCode as a docked
harness and the harness router for spawned subagents are merged, registered
and unit-tested; neither OpenCode nor a routed run is verified at runtime yet.
The test to run before marketing is
[What a successful test looks like](docs/guides/install.md#what-a-successful-test-looks-like).

## Ship

### M0 — the name is final (gate G0)

The product is Warding, the CLI is `warding`, the mark is the Ward Seal
([ADR 0008](docs/adr/0008-product-rename-warding.md)). Done in this tree:
console script, banner, dashboard product name, PWA manifest, Electron
`productName`, README and root docs, brand assets.

Owner-only, still open: trademark knockout on "Warding", "Warding Labs" and
the phonetic Warden / AI Warden cluster (classes 9 and 42); buy the domain and
301 `getjunction.dev` to it; claim the GitHub org, npm, PyPI and social
handles in one hour; publish "Warding has no token or coin". If the knockout
comes back unclear, the fallback name is Keeplit, already checked, without a
fourth round.

### M1 — the first run is true (gates G1, G2, G4, G6)

- **Claude Code works on first message with only `claude` on PATH.** The
  ACP project's `claude-agent-acp` adapter is fetched with `npx` on first run
  (`src/junction/acp/runtimes.py`). Green on code; re-verify on a clean Mac.
- **One-line install under two minutes on a clean Mac and a clean Ubuntu
  VPS.** A wheel with the prebuilt `static/dist`, `pipx` / `uv tool install`,
  checksums, and `scripts/get-junction.sh` downloading the wheel instead of
  cloning. Pointers: `pyproject.toml` (name, scripts, package data),
  `minimal_install.sh`, `.github/workflows/`. `temp-screenshots/` is pruned
  from the tree in this cut.
- **The default build contacts no vendor-owned host** and no vendor
  publisher label is in the UI. Green on code; the `lsof` run is still to be
  recorded and published.
- **Non-Kiro dashboard parity.** `GET /api/models` returns the docked
  harness's advertised set or an honest "this harness picks its own model"
  state instead of a 503; background helpers (titles, suggestions, summaries)
  run on the selected harness through `resolve_usable_model` or degrade
  quietly. Pointers: `src/junction/dashboard/handlers/agents.py`,
  `src/junction/session.py` (`get_bg_session`), `acp.client.resolve_usable_model`.
  Partly on `main`: `/api/models` lists the active harness's advertised
  models (its newest live session, else its last connection check, `503`
  `harness_models_pending` until one exists), and background one-liners,
  task-runner steps, regenerate and rewind run on the active harness; the
  "picks its own model" state and a clean-machine re-verify are still open.
- **Sandbox fail-closed UX.** One screen with the exact
  `sudo warding sandbox install` line on Ubuntu ≥ 23.10 and for containers
  without user namespaces and Windows; Settings → Security shows the per-OS
  table; never weaken the default. Pointers: `src/junction/sandbox.py`,
  `src/junction/security_posture.py`, `docs/guides/install.md`.
- **Measurement.** Privacy-friendly site analytics, email capture with a
  working fallback, GitHub traffic export, an opt-in beacon to an owned
  endpoint or none.

### M2 — the proof artefacts (gates G3, G5, G9)

- **A tagged GitHub Release** with notes and SHA-256 checksums; the release
  PR writes the `CHANGELOG.md` section ([release](docs/build/release.md)).
- **The refusal moment in the UI.** Seal stamp plus the audit line with a
  truncated HMAC on every gate deny, through the contributor seam so the OSS
  tree stays clean. Pointers: `src/junction/hooks.py` (`TOOL_DENY`),
  `src/junction/sel.py`, `src/junction/platform/defaults.py`
  (`DefaultDashboardContributor`).
- **`warding charter`** (CLI and dashboard page): renders
  `security_policy.json`, `profiles/` and the effective `POLICY ∩ PROFILE`
  per tool as numbered articles; exports Markdown for reviewers. Pointers:
  `src/junction/security.py` (`_SENSITIVE_HOME_DIRS`), `hooks.py`,
  `security_posture.py`, [governance](docs/system-specs/modules/governance.md).
- **`warding audit verify`** prints chain status in one command with
  `--export json/csv`. Pointer: `src/junction/sel.py`.
- **SECURITY.md and the "break the charter" script.** Ten reproducible
  attempts to read, write, `sed`, symlink, hardlink, `tar`-extract, `python -c
  open()`, redirect, `mv` over and `chmod` the keystone, with the expected
  refusal for each; scope, out-of-scope rows, safe harbour and founder-signed
  bounty terms. Seed: `test/test_denied_commands_security.py`.
- **Every public claim true.** The forbidden-claims test passes on the built
  site; the README obeys the same list
  ([`JUNCTION.md`](JUNCTION.md#the-no-say-list)).

### M3 — the nights (gates G7, G8, G1)

- **Three recorded, unedited Claude Code nights** on a clean Mac mini and a
  clean VPS: a cron job, one Telegram-approved push, one refused `~/.ssh`
  read, a checkpoint resume, a service restart mid-night, `audit verify`
  green, hourly RSS logged. Founder records; agents script. Published as
  dated rows the site renders. This is the kill criterion: no night, no
  launch.
- **Warding's MCP servers to spec-family harnesses** so cron-from-chat,
  mid-turn questions, spawn and memory tools work on Claude Code and Codex,
  within the harness-parity invariants (adapt, never widen the Kiro path).
  Pointers: `src/junction/acp/client.py` (`_claude_session_mcp_servers`),
  `src/junction/agent.py`, [harness-parity](docs/system-specs/modules/harness-parity.md),
  `scripts/check_harness_parity.py`. Until it lands, label "from dashboard
  or CLI".
- **Agent Worlds for the web and for truth:** a hand-raised sprite pose for
  a pending approval, a local-hour window sky, a time-based tick, a draw-once
  path for reduced motion, integer scaling on phones, the brand palette.
  Pointers: `website/src/pages/scenes/OfficeScene.tsx`,
  `website/src/hooks/sceneCanvas.ts`, `website/src/hooks/useSceneInteraction.tsx`.
- **The hero GIF** is cut from the recordings, harness and date in frame,
  never mocked.

### M4 — launch (gate G10)

Founder-only: the Show HN post in the founder's own words from the fact
sheet; issue templates and a "Known limitations" section (the README's
[What we don't claim](README.md#what-we-dont-claim)); Discussions and a chat
group open. Agents monitor issues and hot-fix; nobody posts under the
founder's name.

### M5 — make the brand true, then the revenue true

- **Dawn-expiring approval grants.** A third choice next to Approve / Deny:
  allow `<tool>` until a configured hour, session-scoped, stored on the
  approval record with the chat identity, never a process-wide `/yolo`; make
  `/yolo` itself deniable by policy. Pointers:
  `src/junction/messaging/approval.py` (`_grant_session_trust`),
  `src/junction/hooks.py`, the channel transports' button renderers,
  governance `SCOPE_CATALOG` (a data change, not an evaluator edit).
- **The Morning Report.** On first dashboard open after an overnight job:
  sessions run, PRs and artifacts, approvals asked and answered, commands
  refused (from the audit log), secrets redacted, wall time; posted to the
  owner's channel and as a dashboard card, plus the "desk stopped at 00:10:
  reason" line so a dead night is reported. New module beside
  `src/junction/cron.py`, `sel.py`, `messaging/approval.py`.
- **`warding switch <runtime>`** validates the runtime, sets
  `agent.acp_backend`, drains and restarts sessions, runs a smoke prompt, and
  prints the carried-over list (memory rows, crons, skills, channels, policy
  hash). Pointers: `src/junction/cli.py` (`config set`, `planes`),
  `src/junction/config/loader.py` (`_normalize_acp_backend`),
  `src/junction/planes.py`, `src/junction/snapshot.py`.
- **Founding Supporter deliverables and `warding license activate`.** A
  Supporter scene on the 440×300 engine, a theme pack in the L1 format, a
  numbered seal badge from a license key. Art commissioned from a named artist
  with a written provenance list. Pointers: `website/src/pages/scenes/config.tsx`,
  [themes](docs/system-specs/modules/themes.md), `platform/discovery.py`.
- **The registry and the verification log from CI.** An e2e job per harness
  (Claude Code, Codex, Goose first) that seeds memory, fires a cron,
  round-trips a Telegram approval and logs a refusal; writes a dated matrix
  with honest "unverified" rows. Pointers:
  [harness-parity-gate](docs/ci/harness-parity-gate.md), `test/`.
- **Approvals on the chat-only channels:** interactive cards on Feishu,
  template cards on WeCom, typed replies on iMessage, waitlist-ordered.
  Pointers: `src/junction/feishu/`, `src/junction/wecom/`,
  `src/junction/imessage/`, `messaging/approval.py`
  (`TextReplyApprovalDecider`).
- **The pilot build:** multi-approver sets per channel, per-channel policy
  profiles, audit-log webhook forwarding. Pilot-funded. Pointers:
  `src/junction/messaging/identity.py`, `messaging/session_trust.py`,
  `platform/admission.py`, `platform/defaults.py`, `sel.py`.
- **RSS under load measured** on an 8 GB Mac mini and a 4 GB VPS, published
  in the README's limitations. Pointer: `src/junction/cloud/sizes.py`.

## Kill criteria

No Claude Code night completes unattended on a clean Mac mini: launch waits.
The trademark knockout returns a live conflict: rename to Keeplit before any
paid item is listed. No outbound security lead takes a call: the pilot is
withdrawn and Team stays a waitlist. A public page element is shown from a
harness other than the one it names: pull it within the hour and publish the
correction.

## Maintain

The loop is event-shaped, not calendar-shaped.

1. **Scout.** An agent (or Dependabot) finds a defect, a stale catalog slug,
   a brand leftover, or a CI flake, and files an issue. It opens no PR from
   the scout run unless the issue is already labeled `agent-os/ready`.
2. **Implement.** A second agent picks `agent-os/ready` issues, works on a
   branch, opens a draft PR, and waits.
3. **Review.** A third agent reviews (tests, keystone, harness parity,
   identity, the NO-SAY list). It may request changes or label
   `agent-os/approved`.
4. **Merge.** A human merges. Agents never merge, never approve their own
   PRs, never push to `main`.
5. **Adversarial pass.** After a security, identity or catalog cut, a
   read-only review agent rewarded for finding bugs files what it finds and
   does not edit in the same turn.
6. **Catalog refresh.** When the upstream registry changes, update
   `model_router/catalog.json` as a snapshot — slugs and labels only.
7. **Security floor.** Keystone, governance, `CONTRACT_VERSION` 1, computer
   use in band, positive harness identity. Importing changes from elsewhere must not
   weaken them or restore Channels / Board.
8. **Truth.** Every screenshot and GIF frame carries its harness and date;
   every checkmark links to a dated row; a correction is published where the
   claim was.
9. **CI.** Keep the gates. A flake is a bug, not a rerun.

The handoff contract is [ADR 0006](docs/adr/0006-agent-os-no-automerge.md).
