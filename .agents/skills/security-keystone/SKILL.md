---
name: security-keystone
description: "Security ceiling and harness-parity floor. Use when editing security.py, hooks, sensitive paths, governance, computer use, or harness identity. Do not weaken keystone, POLICY∩PROFILE, CONTRACT_VERSION 1, in-band computer-use refusals, or positive identity tests."
---

# Security keystone

Overlay ADR: [`../../../docs/adr/0004-security-unchanged.md`](../../../docs/adr/0004-security-unchanged.md).
Do not weaken these. Read the owning specs, do not copy them here:

- [`../../../docs/system-specs/modules/security.md`](../../../docs/system-specs/modules/security.md)
- [`../../../docs/system-specs/modules/sel.md`](../../../docs/system-specs/modules/sel.md)
- [`../../../docs/system-specs/modules/governance.md`](../../../docs/system-specs/modules/governance.md)
- [`../../../docs/architecture/security-deep-dive.md`](../../../docs/architecture/security-deep-dive.md)
- [`../../../docs/system-specs/modules/computer-use.md`](../../../docs/system-specs/modules/computer-use.md)
- [`../../../docs/system-specs/modules/harness-parity.md`](../../../docs/system-specs/modules/harness-parity.md)

## Floor

- Keystone paths under the data home stay in
  `security._SENSITIVE_HOME_DIRS` (policy, profiles, admission,
  computer-use JSON), including write and extract verbs.
- Governance: `effective = POLICY ∩ PROFILE` at this gateway's own
  PreToolUse gate.
- `CONTRACT_VERSION` stays `1` pre-launch.
- Computer use refusals run in band on `tools._dispatch`, never at the
  fail-open hooks gate. No `computer_use.*` scopes.
- Harness identity is positive. `is_kiro_cli` is the fail-OPEN sandbox
  waiver — do not grant it to a harness without an internal sandbox.
- Denied-command **counts** are pinned by
  `test/test_denied_commands_security.py`, not by prose.
