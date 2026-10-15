# Architecture Decision Records

Short, numbered records of product and architecture decisions for Warding.
These are not RFCs: they describe **what was decided**, not a proposal still
under debate. For design proposals see
[../request-for-change/](../request-for-change/README.md).

| ADR | Decision |
|---|---|
| [0001 — Product identity](0001-product-identity.md) | One product name on every surface, and the brand gate that keeps the upstream identity out. The name is set by 0008. |
| [0002 — Two planes](0002-two-planes.md) | The harness registry and the model catalog are composed, not dumped. |
| [0003 — Sidecar not vendor](0003-sidecar-not-vendor.md) | Do not vendor Codex Router. The install-a-sidecar consequence is superseded by 0007. |
| [0004 — Security unchanged](0004-security-unchanged.md) | Keystone, governance, `CONTRACT_VERSION` 1, computer use in-band, positive harness identity. |
| [0005 — Preview not production](0005-preview-not-production.md) | PR and `site/` preview only; no merge, Pages-on-main, DNS, spend, or PyPI. |
| [0006 — Agent OS, no auto-merge](0006-agent-os-no-automerge.md) | Scout files, implementer PRs, reviewer labels; a human merges. |
| [0007 — Built-in model catalog](0007-builtin-model-catalog.md) | `warding up` serves loopback health and a names-only catalog. No provider forwarding, no vendored tree. |
| [0008 — Product name](0008-product-rename-warding.md) | The product is Warding, the CLI is `warding`, the mark is the Ward Seal, the site is warding.dev. |
| [0009 — Attribution and identity boundaries](0009-attribution-and-identity-boundaries.md) | Proposed: preserve original NOTICE attribution, retire inactive scrub exceptions, keep security targets and reconcile the auto harness default. |

Identity and envelope: [`../../WORKING_BRIEF.md`](../../WORKING_BRIEF.md).
Architecture thesis: [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).
