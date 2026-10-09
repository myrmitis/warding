# Security Policy

Warding gives a coding agent real tool access on your machine, so its controls
are enforced at the runtime boundary rather than by prompt instructions alone.
This file says how to report a problem, what is in scope, and where each
control holds and where it does not. The architecture is in the
[security deep dive](docs/architecture/security-deep-dive.md); the mechanism
specs are [security](docs/system-specs/modules/security.md),
[governance](docs/system-specs/modules/governance.md) and
[sel](docs/system-specs/modules/sel.md). Warding is unaudited by a third
party.

## Reporting a vulnerability

Do **not** open a public GitHub issue. Report privately:

- **GitHub:** [private vulnerability report](https://github.com/myrmitis/warding/security/advisories/new)

Include a description, steps to reproduce, the impact, and a suggested fix if
you have one. Reports are acknowledged within five business days. Warding is
run by a single maintainer; a fix for a critical issue is prioritised over all
other work, and the advisory names the release that carries it.

## Supported versions

There is no tagged release yet. Until one exists, `main` is the supported
line; once releases exist, only the latest release receives security patches.

## Scope

This policy covers the source code in this repository and the dependencies it
bundles. It does not cover the coding-agent CLIs Warding launches, the model
providers they talk to, the chat platforms it connects to, or the operating
system it runs on.

### What is enforced where

| Control | Where | Fails |
|---|---|---|
| Keystone paths (`security_policy.json`, `profiles/`, `admission_policy.json`, `computer_use.json` under the data home; `~/.ssh`, `~/.aws`, `~/.gnupg`, …) | Warding's PreToolUse gate, plus the OS sandbox's bind rules where a backend exists | closed |
| Denied commands (`BUILTIN_DENIED_RULES`) | PreToolUse gate | closed |
| `POLICY ∩ PROFILE` for tools and MCP calls | PreToolUse gate | closed for a denied call; **open for a tool the harness pre-authorised**, because a pre-authorised tool can skip the hook |
| Computer use | in band on the tool dispatch path, never at the hook | closed; off by default; one operator opt-in on the keystone file |
| Credential redaction | one chokepoint before a chat surface or the log | always on, no policy key |
| Audit log (HMAC-SHA256 chain) | `security_events.jsonl`, key outside the log directory | write on a nested passthrough is best effort: logs loudly and proceeds |
| OS sandbox (namespaces on Linux, Seatbelt on macOS) | agent subprocess spawn | closed where no backend exists (Windows, containers without user namespaces, Ubuntu ≥ 23.10 until `sudo warding sandbox install`) unless the operator opts in with a loud warning |
| App manifest permissions | advisory | open on an empty allowlist |
| Admission policy | fleet seam | an absent policy admits (the public edition ships none) |
| Owner lock on chat channels | messaging identity | no-op until `WARDING_OWNER_ID` is set |

If you rely on a control that reads "open" here, do not run unattended. They
are listed so you do not have to find them.

## Bypass reports

A bypass is in scope when the agent, through its tool path with the gate and
the sandbox enabled, reads or writes a keystone path, runs a command a
built-in deny rule covers, or executes a tool call that `POLICY ∩ PROFILE`
denies. The rows marked open above are documented behaviour, not bypasses;
each is tracked as an issue.

A reproducible "break the charter" script — a fixed set of attempts against
the keystone with the expected refusal for each — and the reward terms for a
confirmed bypass are in development and will be published here once the
maintainer has signed them. Until then, a confirmed bypass is credited in the
advisory and in the release notes, with the reporter's consent.

Good-faith research that stays within this scope, does not touch other
people's data or machines, and gives us a reasonable time to fix before
disclosure will not be met with legal action from this project.
