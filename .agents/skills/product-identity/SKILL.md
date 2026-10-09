---
name: product-identity
description: "Warding product identity. Use when naming the product, CLI, tagline, README/site/CLI chrome, security claims, or deciding whether an identifier may change. The Python package and CLI are warding. Carries the NO-SAY list and prevents the retired brand token in new prose."
---

# Product identity — Warding

The product is **Warding**. One word, capital W, WAR-ding. Company: Warding
Labs. CLI `warding`. Tagline:
The lamp stays on. The rules stay shut.

Read first: [`../../../WARDING.md`](../../../WARDING.md) (the overlay and
the NO-SAY list), [`../../../WORKING_BRIEF.md`](../../../WORKING_BRIEF.md),
[`../../../PRODUCT.md`](../../../PRODUCT.md),
[`../../../docs/adr/0008-product-rename-warding.md`](../../../docs/adr/0008-product-rename-warding.md).

## Rules

- One sentence, everywhere long copy starts: Warding runs the coding agent
  you already pay for, all night, on your own box, and can ask you in chat
  before it acts when you enable approvals — under a policy it cannot read
  or rewrite. Approvals are opt-in: `agent.approval_mode` defaults to `auto`;
  set it to `interactive` or choose Interactive in the dashboard. Never restore
  an unconditional promise that the default install asks before acting.
- The brand gate fails any added line that spells the retired product name in
  any joining, its hosts, its bundle id or its GitHub organisation; no file is
  exempt. Never Kiro in the name, tagline, logo or domain.
- Not the product: Codex Router, Hearth, Relay, Rudder, and the Warden
  cluster of other companies' products.
- Never headline with an owned phrase (control plane, orchestrate, mission
  control, autopilot, while you sleep, from anywhere, AI teammate, …) and
  never state an untrue claim (side by side, routes your models, works out
  of the box, `pip install`, hosted, teams, overnight verified, any count of
  stars or users). The full list is in `WARDING.md`.
- Every security claim names its mechanism in the same sentence and carries
  "unaudited by a third party" where the charter is described. The model
  catalog lists names and is never a headline.
- Label unshipped things in development: `warding charter`, `warding audit
  verify`, the Morning Report, dawn-expiring grants, wallpaper export, the
  bypass script and bounty.
- Identifiers: Python package and console script `warding`, `WARDING_*` environment
  variables (there is no other prefix), the data home `~/.warding`
  (overridden by `WARDING_HOME`; there is exactly one), GitHub slug
  `myrmitis/warding`, Electron package name `warding-desktop`.
- `SITE_URL` is `https://warding.dev`.
- Do not edit `CHANGELOG.md` on a feature PR.
