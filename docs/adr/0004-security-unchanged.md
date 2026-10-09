# ADR 0004 — Security and harness-parity unchanged

- Status: accepted
- Date: 2026-09-19

## Context

The Warding overlay adds a product name, a model-plane observer, and
CLI chrome. None of that is a reason to retarget the security ceiling or
to express “this is the Kiro harness” as the absence of another harness.

## Decision

Security and harness-parity invariants stay as the router in
[`../../AGENTS.md`](../../AGENTS.md) states them. The overlay does not
weaken them.

In particular:

- **Keystone.** `security_policy.json`, `profiles/`,
  `admission_policy.json`, and `computer_use.json` under the data home
  stay in `security._SENSITIVE_HOME_DIRS`. The agent can neither read nor
  write its own ceiling. Sensitive-path and bash-command matchers keep
  covering those leaves, including write and extract verbs.
- **Governance.** `effective = POLICY ∩ PROFILE`, tightest-wins, at this
  gateway's own PreToolUse gate. The evaluator stays scope-name-agnostic.
  Adding a scope is a `SCOPE_CATALOG` data change, never an evaluator
  edit. Do not add `computer_use.*` scopes for the model plane.
- **`CONTRACT_VERSION` stays pinned at 1** (`platform/context.py`)
  pre-launch.
- **Computer use stays ungoverned by scopes.** Refusals run in band on
  `tools._dispatch`, never at the fail-open `hooks` gate.
  `click_method: "auto"` must never resolve onto `"global"`.
- **Harness identity is positive.** `is_kiro_backend` /
  `== ACP_BACKEND_KIRO`, or membership in a named `ACP_BACKENDS_*` set.
  Never a bare string literal, an inequality, or a negation. An added
  harness adapts; it does not widen the Kiro path.
  `is_kiro_cli` remains the fail-OPEN sandbox waiver and is not granted
  to a harness without an internal sandbox.

Denied-command rule counts are not restated here;
`test/test_denied_commands_security.py` pins them.

## Consequences

- Model-router health/status is observe-only. It does not punch the
  keystone, log secrets, or store provider keys in `WARDING_HOME`
  outside the router's own secret-entry rules.
- Specs:
  [`../system-specs/modules/security.md`](../system-specs/modules/security.md),
  [`../system-specs/modules/governance.md`](../system-specs/modules/governance.md),
  [`../system-specs/modules/harness-parity.md`](../system-specs/modules/harness-parity.md),
  [`../architecture/security-deep-dive.md`](../architecture/security-deep-dive.md).
