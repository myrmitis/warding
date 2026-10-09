# ADR 0006 — Agent OS loop, no auto-merge

- Status: accepted
- Date: 2026-09-20

## Context

Warding is built by cloud agents. The operator asked for a closed loop:
one agent finds issues, another implements them, a third approves and
merges. Auto-merge of agent-authored PRs is a supply-chain hole: a
prompt-injected scout, a compromised dependency, or a confused reviewer
could land code on `main` with no human in the path. The authority
envelope already forbids merge to `main`
([ADR 0005](0005-preview-not-production.md)).

## Decision

Three agent roles, one human merge.

| Role | Trigger | May | Must not |
|---|---|---|---|
| Scout | Schedule or a follow-up | File GitHub issues; label `agent-os/triage` | Open a PR; edit product code in the same turn |
| Implementer | Issue labeled `agent-os/ready` | Branch `cursor/*`, commit, push, open a **draft** PR | Merge; approve its own PR; push to `main` |
| Reviewer | Draft PR from an implementer | Review, request changes, label `agent-os/approved` | Merge; dismiss required reviews; apply `agent-os/approved` to its own PR |
| Human | `agent-os/approved` + green CI | Merge, buy domains, attach DNS, publish | — |

Cursor Automations that spawn those roles are created in the Cursor
dashboard. This repository documents the contract and can comment on
mislabeled PRs; it cannot register dashboard automations from a GitHub
workflow.

## Consequences

- `.github/workflows/agent-os-handoff.yml` reminds, it does not merge.
  It listens to `issues.labeled` only (that event already covers PRs) and
  pins `actions/github-script` by SHA.
- Labels `agent-os/triage`, `agent-os/ready`, and `agent-os/approved` are
  created once on the GitHub repo. This workflow does not mint them.
- Adversarial review is a scout: findings become issues, not a silent
  patch on the same turn.
- Keystone, harness-parity, and identity gates still apply to every
  implementer PR.
- Roadmap: [`../../ROADMAP.md`](../../ROADMAP.md) Maintain.
