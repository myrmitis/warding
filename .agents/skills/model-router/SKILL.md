---
name: model-router
description: "Junction model plane: the loopback catalog junction up starts. Use when changing health/status, catalog, role DAG, or the :4202/:4200 probes. Do not vendor the Node tree, forward provider traffic, log secrets, or crash the gateway when the catalog is down."
---

# Model router — serve the catalog, do not vendor

Contract: [`../../../docs/system-specs/modules/model-router.md`](../../../docs/system-specs/modules/model-router.md).
Code: `src/junction/model_router/`. ADRs
[0002](../../../docs/adr/0002-two-planes.md),
[0003](../../../docs/adr/0003-sidecar-not-vendor.md),
[0007](../../../docs/adr/0007-builtin-model-catalog.md).
Provenance: [`../../../docs/provenance/codex-router.md`](../../../docs/provenance/codex-router.md).

## Rules

- `junction up` serves `/health` and `/catalog` on loopback. Writes,
  including completions, return 501 `model_router_no_forward`.
- If the catalog listener is absent, the ACP gateway still runs (degraded).
  `:4200` is probed and not bundled.
- Never log secrets. Never paste provider keys into chat. Never claim a
  sidecar injects keys.
- Do not copy tray, widget, Electron, HTTPS tunnel, or ACP agent
  bridges. Do not reimplement LiteLLM.
- Catalog JSON copies slugs and labels only. Never hardcode a model id
  as a default; unpinned roles stay `"auto"`.
