# Warding — task map

**A dated local handoff.** GitHub issues own status: bugs, features, and stories
live there. The *why* lives in the ADRs ([`adr/`](adr/README.md)); the
*direction* lives in [`../ROADMAP.md`](../ROADMAP.md). This file says what is in
flight and where. Local work is real, just unmerged; merged is not released.
Envelope: [`../WORKING_BRIEF.md`](../WORKING_BRIEF.md). Agent loop:
[ADR 0006](adr/0006-agent-os-no-automerge.md).

## Where work is tracked

| Surface | Owns | Published? |
|---|---|---|
| GitHub issues (`bug`, `enhancement`, `documentation`) | Status of every bug, feature, and story | Yes — issues own status |
| [`docs/adr/`](adr/README.md) | Decisions and their rationale (*why*), frozen once accepted | Yes |
| [`../ROADMAP.md`](../ROADMAP.md) | Merged milestones and the maintain loop | Yes |
| This file | Local, in-flight lanes and where they live, as of a date | No — a dated local handoff |

The operator's portfolio memory lives in `~/dev/memory/INDEX.md` on the
operator's machine. It is a **reference, not authority**: it carries reviewed
conventions, lessons, and pointers, but each repository owns its own facts,
contracts, and work state. A memory record never overrides this repo's
`AGENTS.md`, ADRs, or code.

**Writing to memory.** When a session learns something reusable — a convention,
a lesson, a pointer — propose it as a record under that repository's own rules,
with the exact source. An agent never self-publishes memory. An operator merge
makes the record an accepted **reference**; the owning repository always stays
authoritative, so a record never overrides this repo's `AGENTS.md`, ADRs, or
code. This is a shared **file read/write protocol** only; automatic
cross-harness memory import (hooks that sync memory between harnesses) is not
installed.

## Start and finish

**Start of a session**

1. `git fetch`; compare your branch with `origin/main` so you know what is
   *merged* (on `main`) versus *local* (unpushed, on a branch).
2. Read the open GitHub issues (they own status) and this file for in-flight
   lanes.
3. Read `~/dev/memory/INDEX.md` for prior lessons and conventions (reference,
   not authority).
4. Open the owning doc for the subsystem from the routing table in
   [`../AGENTS.md`](../AGENTS.md) before editing code.

**Finish of a session**

1. File or update a GitHub issue for every bug, feature, or story: it is the
   published record. Apply an existing label (`bug`, `enhancement`,
   `documentation`, `readiness:*`); do not mint a new taxonomy.
2. If a decision was made, write it as an ADR (the *why*), not into this file.
3. If the session learned a reusable lesson or convention, propose a memory
   record (the "Writing to memory" rule above); it is an accepted reference
   once the operator merges it, never authority over this repo.
4. Update this file only for local, unpublished state.
5. Run [`./scripts/docs-lint.sh`](../scripts/docs-lint.sh) when docs changed.
6. **Record, do not publish.** Leave the branch, the changed paths (committed or
   not), the test command and its result, and the next action where the next
   session will find them. Commit and push only when explicitly authorized; a
   lane is not on `main` until a human merges it
   ([ADR 0005](adr/0005-preview-not-production.md),
   [ADR 0006](adr/0006-agent-os-no-automerge.md)).

## In flight

Nothing is recorded here yet. When a lane is started and not yet merged, add one
row: the branch, the worktree it lives in, what it is for, its state (what was
run, with the command and its result), and the GitHub issue that owns its
status. Remove the row when the lane merges; the issue and the commit history
are the record from then on.

| Branch | Worktree | Lane | State | Issue |
|---|---|---|---|---|
| — | — | — | — | — |

**Next action.** Lanes are unmerged and not committed to `main`. Commit and push
require an explicit user instruction, and a lane is not on `main` until a human
merges it. Full CI and a live-harness run are separate from a focused-suite
result; record which one a row's state refers to.

## Out of scope for agent lanes

Merging, releasing, paid infrastructure, and auto-merge of agent pull requests
stay with a human ([ADR 0005](adr/0005-preview-not-production.md),
[ADR 0006](adr/0006-agent-os-no-automerge.md)). `CHANGELOG.md` is written only
when a version is bumped (see [`../AGENTS.md`](../AGENTS.md)).
