# ADR 0002 — Two planes, composed not dumped

- Status: accepted. The optional-sidecar model plane is superseded by [0007](0007-builtin-model-catalog.md). Two-plane composition still holds.
- Date: 2026-09-19

## Context

This checkout already docks multiple ACP agents. Codex Router already
routes inference for those agents to other providers. Putting both in one
product is the Warding thesis. The failure mode is a dump: copy a Node
tree into the Python package, collapse two processes into one, and inherit
tray, tunnel, and agent-bridge surfaces this gateway already covers.

## Decision

Warding is two planes composed behind one CLI and dashboard:

1. **Harness plane** — ACP runtime registry
   (`src/warding/acp/runtimes.py`). Default `agent.acp_backend` is
   `auto`. `kiro-cli` is optional.
2. **Model plane** — optional Codex Router sidecar on loopback (typically
   `:4202` + LiteLLM `:4200`), observed from
   `src/warding/model_router/`.

Memory, cron, and skills stay on the Python gateway. If the sidecar is
absent, the gateway still runs as an ACP control plane (degraded,
documented).

Do not dump Codex Router into `warding`. Do not re-land multi-ACP; it is
already on `main`.

## Consequences

- Architecture prose lives in [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).
- Sidecar vs vendor is [0003](0003-sidecar-not-vendor.md).
- Health/status contract:
  [`../system-specs/modules/model-router.md`](../system-specs/modules/model-router.md).
- Agents may later set `openai_base_url` at the sidecar; that is M2, not a
  license to vendor.
