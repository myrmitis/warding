# Request for Change

Design documents for changes that are large enough, risky enough, or contested
enough to be worth writing down before building. An RFC here is a **proposal and
a record of a decision** — not a description of what the code does today. For
that, read the code, or the `status` field described below.

## Index

Each status was checked against the code (definitions *and* callers), not taken
from the document's own claims.

| Document | Status | What is actually in the code |
|---|---|---|
| [rfc-durable-run-coordinator.md](rfc-durable-run-coordinator.md) | `draft` | Nothing. Design and a staged additive migration only; the existing in-memory manager and run folders remain authoritative |
| [rfc-issue-radar-stewards.md](rfc-issue-radar-stewards.md) | `draft` | Nothing. Design of record only; `steward_brief.md` and `steward_ledger_spec.md` sit beside the Issue Radar backend as companion specs, also unimplemented |
| [rfc-orchestrator-chat-sessions.md](rfc-orchestrator-chat-sessions.md) | `partial` | Multitask Mode shipped and has since received store and routing fixes. The implementation deliberately diverges from the RFC in at least three places: no snapshot-generation CAS, no `release` decision action, and immediate per-result delivery instead of burst coalescing |
| [rfc-channel-plugin-architecture.md](rfc-channel-plugin-architecture.md) | `partial` | Shared turn pipeline shipped; **4 of 7** channels adopted. Registry/seam collapse, telegram+discord, Feishu unstarted. Its §9 address rule is only partly honored: the address-agnostic pipeline is pinned in code, the single builder/parser is not |
| [rfc-local-notification-bus.md](rfc-local-notification-bus.md) | `partial` | Phases 1/3/4 complete. Phase 2 wired but has no producer; Phase 5 shipped 2 of 3 |
| [rfc-federated-app-platform.md](rfc-federated-app-platform.md) | `partial` | Phase 1 substantially shipped, Phase 3 half-built. Phase 2, Phase 1's removals, Phase 4, Phase 5 unstarted |
| [rfc-notification-bridge.md](rfc-notification-bridge.md) | `accepted` | Nothing — zero implementation code |
| [rfc-tips-kit.md](rfc-tips-kit.md) | `draft` | Nothing. An earlier T1 attempt was **retracted**; the design section needs revising first |
| [rfc-app-sandbox-isolation.md](rfc-app-sandbox-isolation.md) | `draft` | Nothing. Apps still run in-process with full privileges (see `src/junction/docs/app-platform-trust-model.md`); no isolation code exists |
| [rfc-issue-radar-dispatch.md](rfc-issue-radar-dispatch.md) | `draft` | Nothing. Issue Radar has Investigate and Review; no verb produces work, and issues carry no link to the change that resolves them |
| [rfc-token-efficient-monitors.md](rfc-token-efficient-monitors.md) | `draft` | Nothing. Probe-first replacement for token-heavy babysit loops |
| [rfc-tailnet-dashboard-access.md](rfc-tailnet-dashboard-access.md) | `partial` | Phase 1 landed — reports the pin's real scope, does not fix it. Phases 2–4 unstarted, including the pin repair |
| [rfc-s3-backup.md](rfc-s3-backup.md) | `draft` | Nothing. `VALID_COMPONENTS` carries no session component and no code path writes Junction's state to a remote store |
| [rfc-navigation-placement-seam.md](rfc-navigation-placement-seam.md) | `draft` | Nothing. `UISidebar` ships in the manifest and no frontend code reads `ui.sidebar`; `appNavTarget` still resolves `pages[0]` only, and `registerBuiltinSurface` is not one of the nine edition seams |
| [rfc-append-only-session-transcript.md](rfc-append-only-session-transcript.md) | `draft` | Nothing. `_save_slot_to_history` still re-serializes the whole in-memory window on every flush, and `rewrite_session` / `sliding_window` still have no production caller |
| [rfc-everything-is-an-app.md](rfc-everything-is-an-app.md) | `draft` | Nothing. The eleven declared-but-unread manifest fields it inventories are all still declared and still unread; the rule itself is tenet 8 in [`TENETS.md`](../../TENETS.md), argued in [rfc-amend-tenets-everything-is-an-app.md](rfc-amend-tenets-everything-is-an-app.md) |
| [rfc-amend-tenets-everything-is-an-app.md](rfc-amend-tenets-everything-is-an-app.md) | `accepted` | Tenet 8 is in [`TENETS.md`](../../TENETS.md); the RFC records why it was added, how it is ordered against the other seven, and how its two most quotable clauses should be read |
| [rfc-projects.md](rfc-projects.md) | `draft` | Nothing. No project manifest format exists, `slot.project` is a bare directory path, and no code references Confluence or ServiceNow |
| [rfc-tool-derived-diff-cards.md](rfc-tool-derived-diff-cards.md) | `in-progress` | Shipped: dashboard diff-card/summary promotion + runtime-selected prompt rule. The messaging `OutputEvent` extension (§3.3) is unstarted |

Nothing in this directory is `implemented` or `superseded` today.

## Front matter

Every document carries YAML front matter as the machine-readable record. The
prose header below it stays human-readable and carries the *why*; front matter
carries the *what*.

```yaml
---
title: Channel Plugin Architecture — shared runtime, channels as app extension points
status: partial            # see vocabulary below
author: Junction contributors
created: 2026-07-28
last-audited: 2026-08-03   # when status was last verified against code
supersedes: []
superseded-by: []
---
```

Optional keys: `kind: framework` for docs that are policy rather than a
reviewable change to a named component, and `revision:` where a document is
versioned across review rounds.

`last-audited` exists because a bare `status: partial` rots silently. If it is
far behind the code, distrust the status.

### Status vocabulary

| Status | Meaning |
|---|---|
| `draft` | Proposed. Nothing built. |
| `accepted` | Design agreed and locked. Nothing built yet. |
| `in-progress` | Implementation is live in an open pull request or an active branch. |
| `partial` | Some phases are in the code; the rest are open. The prose status line names which. |
| `implemented` | Every phase is verifiably in the code. |
| `superseded` | Replaced. `superseded-by` names the replacement. |

`partial` is the most common status and the most dangerous one to read
carelessly — several documents here describe a plan the code only partly
follows, and some describe a plan the code **deliberately diverged from**.

## Reading a `partial` or divergent RFC

Two failure modes are live in this directory. Each document's prose status line
calls out its own, but the patterns are worth knowing before you trust any of them:

1. **The plan was overtaken.** A probe phase returned a negative verdict, or a
   later change affirmatively reversed a phase, and the document was not revised
   afterwards. What shipped is then not what the phases below it describe.
   The remedy is a note at the head of the affected section that says which
   decisions were reversed, so the reasoning survives as a record without still
   reading as the contract.
2. **A dependency claim is overstated.** A document asserts that another
   proposal's phases "all shipped". The phases the document actually needs may be
   real while the blanket claim is not.

When a document and the code disagree, the code wins and the document is a bug.
Fix it in the same change that discovers the drift.

## Writing a new RFC

[GOVERNANCE.md](../../GOVERNANCE.md) covers who decides whether an RFC is
accepted, and the scope test for when a change needs one at all.

- File as `rfc-<topic>.md`, kebab-case. Framework or policy docs that propose no
  reviewable change to a named component drop the prefix and set `kind: framework`.
- Open with front matter, then an H1 `# RFC: <Title>`, then the prose header.
- Write in English.
- Structure that has worked here: Summary → Motivation (current state, problems)
  → Goals → Non-goals → Design → Migration plan (phased, each phase PR-sized with
  **exit criteria**) → Backward compatibility → Security considerations →
  Alternatives considered → Open questions.
- Phases earn their keep by being independently shippable and independently
  abandonable. State exit criteria as assertions someone can test, and mark any
  phase whose entry depends on an unanswered open question as blocked on it.
- **Verify before asserting.** Claims of the form "X does not exist" or "Y is
  unused" are the ones that most often turn out wrong. Grep for callers, not just
  definitions — a defined-but-uncalled symbol means the behavior does not happen,
  which is a different (and usually more interesting) finding than absence.
  Cite symbols rather than line numbers where you can, and say when you measured.
- A probe phase that exists to answer a question must write its verdict down
  somewhere durable and the RFC must be updated to point at it, so the document
  does not outlive the answer it was waiting for.

## Keeping this honest

When you land an implementation change for anything here, update the document's
`status` and `last-audited` in the same change, and re-audit the whole directory
whenever the table above starts feeling plausible rather than checked. The audit
is cheap: for each document, extract its named deliverables, grep for each one's
definition and callers, and check which phases are actually live.
