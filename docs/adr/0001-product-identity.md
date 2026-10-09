# ADR 0001 — Product identity and the brand gate

- Status: accepted; the name and mark are set by
  [ADR 0008](0008-product-rename-warding.md)
- Date: 2026-09-19

## Context

`myrmitis/warding` docks multiple ACP agents. User-facing chrome must carry
one product name everywhere: the README, the marketing site, CLI help, and the
dashboard default bot name. The identity of the project this tree started from
must not ship.

## Decision

Every surface carries the product name chosen in ADR 0008.

| Surface | Spelling |
|---|---|
| Prose / dashboard default | Warding |
| Primary CLI | `warding` |
| Product-facing aliases | none |
| GitHub slug | `myrmitis/warding` |
| Python package | `warding` |
| Data home | `~/.warding` |
| Electron id | Warding |

## Consequences

- User-facing overlay this cut: README, `site/`, CLI, dashboard
  `DEFAULT_PRODUCT_NAME` / `bot_name`, brand gate.
- The brand gate (`scripts/check_brand_name.py`) treats the upstream
  identity as retired. On newly added lines it rejects the retired
  product's name glued or joined by one separator (including Unicode
  dashes, `%20` and regex spellings), in prose and identifiers alike;
  its data home, whether spelled as one path (or a regex of one) or built
  from split string literals; its hosts and its bundle id, dots plain or
  regex-escaped; its GitHub org in any use; and its mascot. No file is
  exempt. Warding is accepted. The optional kiro-cli harness keeps its own
  spellings: `kiro-cli`, `~/.kiro` with its own directories and
  `kiro.dev` are not flagged, and neither is the word "crew" on its own.
- Hardcoded catalog descriptions stay a follow-up issue.

## Not decided here

Two-plane composition, sidecar vs vendor, security invariants, and preview vs
production are ADRs 0002–0005. Until those files exist, follow
[`../../WORKING_BRIEF.md`](../../WORKING_BRIEF.md).
