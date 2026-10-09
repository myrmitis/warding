# Working brief — Warding

The product identity, the thesis, and the authority envelope for agents
working in this checkout.

## Identity

| Field | Value |
|---|---|
| Product | **Warding** (company: Warding Labs) |
| CLI | `warding` |
| Tagline | The lamp stays on. The rules stay shut. |
| Promise | Warding runs the coding agent you already pay for, all night, on your own box, and can ask you in chat before it acts when you enable approvals — under a policy it cannot read or rewrite. Approvals are opt-in: `agent.approval_mode` defaults to `auto`; set it to `interactive` or choose Interactive in the dashboard. Chat sessions run the one harness you choose in one setting; spawned subagents can be routed to another installed harness, which the router picks without forwarding provider traffic. No run cap from us; your model plan's limits still apply. Unaudited by a third party. |
| Voice | The night watchman who is also a good notary: calm, dry, exact about time and mechanism. Clock times as nouns. The limit in the same sentence as the feature. The mechanism in every security claim. No owned phrases, no numbers we did not measure, no universal quantifiers about security, no emoji, no exclamation marks. |
| Visual | Paper and the Ward Seal by day (bg `#F3EEE3`, ink `#1A1814`, seal `#B3301A`); the night office by night (bg `#0B0E14`, warm white `#ECE8E1`, lamp `#FFB547`, refusal `#FF7A5C`); factory theme slug `warding`. Mark: the Ward Seal, a keyhole crossed by three ward bars with one drop of wax; the seal is the only mark. Type: Fraunces (wordmark, display) + IBM Plex Sans (body, UI), bundled. Lucide icons only. Motifs: the seal and the refusal, the lit window, the three ward bars; no mascot. Brand kit: `assets/brand/build.py`. |
| Site | https://warding.dev (`www` redirects there). |
| GitHub slug | `myrmitis/warding` |
| Package / data home | `warding`, `WARDING_HOME`, `~/.warding`, Electron package name `warding-desktop`. |

Decision records: [ADR 0008](docs/adr/0008-product-rename-warding.md) (the
name) and [ADR 0001](docs/adr/0001-product-identity.md) (the identity rules
it builds on). Agent overlay: [`WARDING.md`](WARDING.md). Product:
[`PRODUCT.md`](PRODUCT.md).

## Thesis

Warding is a governed late desk for the coding agents you already use. It has a
dashboard, CLI, ten chat apps, cron, task runner, subagents, memory, OS sandbox,
deny rules, keystone policy, HMAC-chained audit log, `POLICY ∩ PROFILE` at the
gate, Agent Worlds, the harness registry with kiro-cli optional and last, a
harness router for spawned subagents, no vendor account in the door, and no
vendor-owned endpoint in the default build.

```
Operator
  → warding CLI / dashboard / chat app
    → Python gateway
      → the docked harness (ACP runtime registry: Claude Code, Codex, Cursor, Goose, OpenCode, …, kiro-cli last)
        · a spawned subagent may be routed to another installed harness (harness router)
      → the gate (keystone paths, denied commands, POLICY ∩ PROFILE, redaction, audit chain)
      → memory, cron, task runner, subagents
      → a model catalog on loopback (names only; /health and /catalog; completions 501)
```

- **Chat runs the harness you choose; subagents can be routed.**
  `agent.acp_backend` defaults to `auto` via `src/warding/acp/runtimes.py`,
  and chat sessions run that one harness. Spawned subagents can be routed to
  another installed harness by the harness router (flat-rate quota before
  metered, task kind, cooldown after a usage limit or failed login); it picks
  a harness and never forwards provider traffic. The router and OpenCode are
  registered and unit-tested, not verified at runtime. Chat sessions on two
  harnesses side by side are not a goal and must not be claimed.
- **The catalog is names only and never a headline.** `warding up` starts
  the listener in `src/warding/model_router/`; completions return `501`; no
  translation gateway is bundled; if the listener is down, the gateway still
  runs (degraded, documented). Warding never mints a provider URL and never
  pastes provider keys into chat. Contract:
  [ADR 0007](docs/adr/0007-builtin-model-catalog.md).
- **Governance is the trust beat, not the headline.** The night is the story;
  the paper-and-seal system is the look; the name is the lock.
- **Every public claim is true today or labelled in development.** Overnight
  runs are unverified on every harness; Claude Code is verified for chat only;
  OpenCode and the harness router are registered · unverified.

## Authority envelope

| Allowed | Blocked |
|---|---|
| Feature branch, commit, push | Merge to `main` |
| Pull request | Production deploy, DNS, domain purchase |
| GitHub issues for epics and lanes | Paid services, PyPI, npm, Docker publish |
| Vercel preview of `site/` | External comms (posts, emails, issues on other repos) |
| Drafts labelled "for founder rewrite" | Posting under the founder's name anywhere |
| | Data deletion, irreversible migrations |
| | GitHub repository or org rename (owner, in Settings) |
| | Any price, term, refund, or security-report reply |
