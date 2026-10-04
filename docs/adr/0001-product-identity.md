# ADR 0001 — Product identity is Junction

- Status: accepted; the name is superseded by
  [ADR 0008](0008-product-rename-warding.md) (the identifiers that stay and
  the brand gate still hold)
- Date: 2026-09-19

## Context

`laqaer/junction` docks multiple ACP agents. User-facing chrome is Junction
in the README, the marketing site, CLI help, and the dashboard default bot
name. Junction is the product of this checkout.

Criteria: one-word CLI; works for **both** “which agent” and “which model”;
local-first; not a clone of an existing gateway / Router / Codex; searchable; low trademark
collision.

## Decision

The product name is **Junction**.

| Surface | Spelling |
|---|---|
| Prose / dashboard default | Junction |
| Primary CLI | `junction` |
| Product-facing aliases | none |
| Tagline | Where coding agents meet the models you want. |
| GitHub slug | `laqaer/junction` |
| Python package | `junction` |
| Data home | `~/.junction` (an existing previous directory is kept) |
| Electron id | Junction |

## Assessment (then the winner)

| Name | Fit | CLI | Collisions | Verdict |
|---|---|---|---|---|
| Hearth | Strong home/memory; weak routing | `hearth` | Hearthstone | Runner-up |
| Relay | Strong routing; weak workspace | `relay` | Many Relays | Reject |
| Rudder | Steer agents + models | `rudder` | RudderStack | Reject |
| Harbor / Quay / Dock | Dock agents | — | CNCF Harbor, quay.io, Docker | Reject |
| Helm / Tiller | Steer | — | Kubernetes | Reject |
| Loom / Warp / Lattice / Nexus | Metaphor | — | Loom, Cloudflare WARP, Lattice HQ, Sonatype | Reject |
| Compass / Pilot / Beacon / Atlas | Navigate | — | Atlassian, many pilots | Reject |
| Chartroom | Owner’s chartingstars.com | `chartroom` | None, but long/obscure | Internal nod only |
| Helix | Persistence | `helix` | Helix editor | Reject |
| Lantern | Local light | `lantern` | Few | Warm but silent on routing |
| Dockyard | Agent home | `dockyard` | Few | Mute on models |
| Portico | Gateway | `portico` | Few | Gateway ≠ two planes |
| Switchboard | Classic routing | `switchboard` | Dated, long | Reject |
| Codex Router | Accurate to one plane | — | Their 3.7k-star product | Never |
| Earlier working titles | Left behind | — | Operator asked to leave them | Never |
| **Junction** | Meeting of agent plane + model plane | `junction` | Minor (git-junction, road signs); no category killer | **Winner** |

Junction names the join: ACP harnesses on one side, model routing on the other.
Hearth was the runner-up (home/memory) and lost because it is silent on routing.

## Consequences

- User-facing overlay this cut: README, `site/`, CLI, dashboard
  `DEFAULT_PRODUCT_NAME` / `bot_name`, brand gate.
- The brand gate (`scripts/check_brand_name.py`) treats the previous
  identity as retired. On newly added lines it rejects the retired
  product's name glued or joined by one separator (including Unicode
  dashes, `%20` and regex spellings), in prose and identifiers alike;
  its data home, whether spelled as one path (or a regex of one) or built
  from split string literals; its hosts and its bundle id, dots plain or
  regex-escaped; its GitHub org in any use; and its mascot. No file is
  exempt. Junction is accepted. The optional kiro-cli harness keeps its own
  spellings: `kiro-cli`, `~/.kiro` with its own directories and
  `kiro.dev` are not flagged, and neither is the word "crew" on its own.
- Hardcoded catalog descriptions stay a follow-up issue.
- Chartroom remains an internal nod only, not a public name.

## Not decided here

Two-plane composition, sidecar vs vendor, security invariants, and preview vs
production are ADRs 0002–0005. Until those files exist, follow
[`../../WORKING_BRIEF.md`](../../WORKING_BRIEF.md).
