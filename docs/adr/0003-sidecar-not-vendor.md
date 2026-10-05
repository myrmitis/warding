# ADR 0003 — Sidecar, not vendor

- Status: accepted. The "operator installs the sidecar" consequence is superseded by [0007](0007-builtin-model-catalog.md). The do-not-vendor list below still holds.
- Date: 2026-09-19

## Context

[Codex Router](https://github.com/duolahypercho/codex-router) is an MIT
local router: Responses on loopback `:4202`, LiteLLM on `:4200`,
namespaced catalog, credential isolation. It also ships tray, widget,
Electron Control Center, a public Cursor HTTPS tunnel, and experimental
ACP agent bridges. Those last surfaces overlap this repository's ACP registry.
Vendoring the tree would copy a second product into the first and fork
LiteLLM by accident.

Apache-2.0 (this tree) and MIT (Codex Router) can combine when copied
bytes keep NOTICE and attribution. This cut copies **no** bytes, so that
question stays idle.

## Decision

Treat Codex Router as an **optional sidecar**. Junction observes and
composes it. Junction does not vendor the Node tree.

Do not copy:

- tray / menu-bar app
- desktop widget
- Electron Control Center
- public Cursor HTTPS tunnel
- experimental ACP agent bridges (Claude / Cursor / Gemini session
  bridges)

Do not reimplement LiteLLM. Do not rewrite the router's secret-entry
rules into `JUNCTION_HOME`.

This cut's Python surface is health and status in
`src/junction/model_router/`. Operator-install of the sidecar is M2.

## Consequences

- Provenance: [`../provenance/codex-router.md`](../provenance/codex-router.md).
- Affiliation: Codex Router disclaims OpenAI / GitHub / Anthropic / and
  the rest. Junction does not claim it either.
- A later vendored *subset* is a new ADR, with NOTICE for any copied
  bytes. It is not this cut.
