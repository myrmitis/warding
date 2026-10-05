---
name: acp-runtimes
description: "ACP runtime registry (harness plane). Use when changing agent.acp_backend, spawn argv, auto default, or adding a harness. Multi-ACP is already on main — do not re-land it. kiro-cli is optional."
---

# ACP runtimes — harness plane

Registry: `src/junction/acp/runtimes.py`. Default `agent.acp_backend` is
`auto`. `kiro-cli` is last in `AUTO_PREFERENCE` and is optional.

Read first:

- [`../../../TREE.md`](../../../TREE.md)
- [`../../../docs/system-specs/modules/harness-parity.md`](../../../docs/system-specs/modules/harness-parity.md)
- [`../../../docs/system-specs/modules/acp-client.md`](../../../docs/system-specs/modules/acp-client.md)
- [`../../../docs/ci/harness-parity-gate.md`](../../../docs/ci/harness-parity-gate.md)

## Rules

- Identity is positive: `is_kiro_backend` / membership sets. Never
  `not is_<other>`.
- An added harness adapts; it does not widen the Kiro path.
- `agent.provider` stays `acp`. The harness is not a second provider.
- Unknown backends degrade to `auto`, not to `kiro-cli`.
- Codex Router's experimental ACP agent bridges overlap this registry.
  Do not copy them ([ADR 0003](../../../docs/adr/0003-sidecar-not-vendor.md)).
