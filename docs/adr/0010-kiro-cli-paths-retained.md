# ADR 0010 — Keep the kiro-cli credential paths and guide

- Status: accepted
- Date: 2026-10-18
- Refines: [ADR 0009](0009-attribution-and-identity-boundaries.md)
- Scope: [identity cleanup #27](https://github.com/myrmitis/warding/issues/27),
  after [#49](https://github.com/myrmitis/warding/pull/49) removed the
  checked-in `.kiro/` directory

## Context

The 2026-10-15 identity grep on #27 left two Kiro items open for the Kiro
removal work: the `amazon-q` credential-store paths, and the kiro-cli
documentation. `WARDING.md` keeps kiro-cli as an optional harness that is
selected last. The harness is not removed. This record decides what the
retained harness keeps.

## Decision

Keep the `amazon-q` and `kiro-cli` credential-store paths in
`src/warding/security.py` (`is_sensitive_path`) and in the audit-only read
list in `src/warding/hooks.py`. Keep the matching readers in
`src/warding/dashboard/handlers/kiro_usage_api.py` and
`src/warding/kiro_prerequisite.py`. Keep the `~/.kiro/settings/amazon-internal.json`
sandbox exclusion in `src/warding/sandbox.py`.

These identifiers name security targets, not product branding. The stores
hold a live SSO bearer token. An agent that reads one can act as the operator
against every SSO-gated service. The `amazon-q` store often holds the same
account as the `kiro-cli` store on the same host, so blocking only one of
them would leave the credential readable. ADR 0009 already keeps legacy
authentication-store protections for the same reason.

Keep [`docs/guides/kiro-cli-mcp-oauth-tokens.md`](../guides/kiro-cli-mcp-oauth-tokens.md).
It documents a retained harness. There is no vendored kiro-cli documentation
tree in this repository; the only Kiro documentation is that guide and the
module specs that describe the kiro-cli transport and sandbox exclusion.

The company-name gate (`scripts/check_company_names.py`) keeps the allowlist
entries for these paths. A change to the list is a security change and
follows [security](../system-specs/modules/security.md).

## Consequences

The `git grep -i amazon` count on `main` does not reach zero. The intended
matches are the ones listed on #27: root `NOTICE`, AWS and Bedrock
identifiers, the scrub and leak-detection patterns, and the paths above.
The pass/fail measure for the identity cleanup is the three identity gates,
not the raw count.

Removing kiro-cli as a harness is a product decision reserved to the owner
(ADR 0009). If the owner takes it, remove the harness, the readers and the
guide together, and keep the sensitive-path entries unless a security review
shows that no Warding host can hold those stores.
