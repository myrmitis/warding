---
name: agent-os
description: Warding agent-OS improvement loop. Use when filing scout issues, picking up agent-os/ready work, or reviewing agent PRs. Never merge. Never approve your own PR.
---

# Agent OS loop

Contract: [`../../../docs/adr/0006-agent-os-no-automerge.md`](../../../docs/adr/0006-agent-os-no-automerge.md).
Envelope: [`../../../WORKING_BRIEF.md`](../../../WORKING_BRIEF.md).

## Roles

1. **Scout** — find defects, file issues, stop.
2. **Implementer** — pick `agent-os/ready`, open a draft PR, stop.
3. **Reviewer** — review someone else's PR, label `agent-os/approved` or
   request changes, stop.

An agent squash-merges once `PR Readiness` passes (owner decision, 2026-10-14).

## Rules

- Merge only after `PR Readiness` passes. Do not push to `main`. Do not approve a PR you authored.
- Do not buy domains, change DNS, or spend.
- Do not weaken keystone or harness-parity.
- Do not edit `CHANGELOG.md`.
- Scout runs are read-only against the tree they review. File issues;
  do not patch in the same turn.
- Implementer branches are `cursor/<name>-55da` (or the current cloud
  suffix) off the agreed base.
- Labels `agent-os/triage`, `agent-os/ready`, and `agent-os/approved`
  must exist on the repo. Create them once; the handoff workflow only
  comments.
