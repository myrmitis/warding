# ADR 0007 — Built-in model catalog

- Status: accepted
- Date: 2026-09-23

## Context

Operators should not install a second product before Junction can show a
model plane. The MIT router this catalog was snapshotted from also ships
a tray app, a desktop widget, an Electron control center, a public HTTPS
tunnel, and experimental ACP agent bridges. Those surfaces overlap
Junction's own dashboard and ACP registry. Copying that tree would put a
second product inside the first. Reimplementing its translation gateway
would fork a large proxy and invent a place to store provider keys.

## Decision

`junction up` starts a loopback listener owned by Junction.

- Bind `127.0.0.1` only. Default port `4202`, overridable with
  `MODEL_ROUTER_PORT` or `CODEX_ROUTER_PORT`.
- `GET /health` and `GET /catalog` only. Catalog bytes are the shipped
  snapshot (slugs and labels). No credentials.
- Completion and other write routes return `501` with
  `code` `model_router_no_forward`. Junction does not pretend to forward
  provider traffic.
- If the port is already taken, leave that listener alone and probe it.
- Do not bundle a translation gateway on `:4200`. Status stays `degraded`
  while only the catalog listener is up. The ACP gateway still runs.
- Do not copy tray, widget, Electron, public tunnel, or ACP agent bridges.
- Do not write provider keys into the data home or into chat.

The default data home for a new install is `~/.junction`. An existing
previous data directory is opened when `~/.junction` is absent. The
security floor covers the current directory and the older ones.

## Consequences

- Supersedes the "operator installs a sidecar" consequence of
  [0003](0003-sidecar-not-vendor.md). The do-not-vendor list in 0003
  still holds.
- Provenance for the catalog snapshot stays in
  [`../provenance/codex-router.md`](../provenance/codex-router.md).
- Contract:
  [`../system-specs/modules/model-router.md`](../system-specs/modules/model-router.md).
