# ADR 0005 — Preview, not production

- Status: accepted
- Date: 2026-09-19

## Context

The bootstrap cut needs a public-looking surface (docs, `site/`, a PR)
without taking production authority. Merge, Pages-on-main, DNS, spend,
and PyPI are irreversible or billable. The envelope in
[`../../WORKING_BRIEF.md`](../../WORKING_BRIEF.md) already splits allowed
from blocked; this record is that split as an ADR.

## Decision

This execution may:

- work on the feature branch and open a pull request to `main`
- open GitHub issues for the epic and lanes
- run CI on the branch
- deploy a Vercel **preview** of `site/` only, hobby plan, no spend

This execution may not:

- merge the PR to `main`
- publish GitHub Pages from `main`
- change DNS
- incur spend (paid Vercel, paid anything)
- publish to PyPI or Docker
- rename the GitHub repository
- send external comms (issues on other repos, email, posts)
- delete data or run irreversible migrations

## Consequences

- M1 ends at an unmerged PR plus preview. Promotion is a later human
  action.
- Roadmap: [`../../ROADMAP.md`](../../ROADMAP.md).
- Lane map: [`../TASK_MAP.md`](../TASK_MAP.md).
