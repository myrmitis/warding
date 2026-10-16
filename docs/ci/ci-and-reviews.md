# CI and the review gates

What runs on a pull request, what each gate is for, and how they fold into one
verdict. The source of truth is `.github/workflows/`; this doc explains the
shape and the rationale.

The `prepare-pr` skill
(`src/warding/builtin_skills/warding-dev/prepare-pr/SKILL.md`) is the agent
side of this: it drives a working tree to review-ready by working with these
gates. Its phase flow, exit-code contract and PR-description contract live in
that skill, not here. Its portability design is
[prepare-pr-portability.md](prepare-pr-portability.md). The human release process
is [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Shape

CI is a **fan-out of independent workflows that one aggregator folds into a single
verdict**:

```
pull_request
  |-- ci.yml            "CI"           lint, sharded tests, coverage gate, e2e
  |-- build.yml         "Build"        wheel + desktop artifacts still build
  |-- site.yml          "Site"         marketing site test+build (path-scoped to site/**)
  |-- code-review.yml   "Code Review"  grep rules, woke, Semgrep, PR hygiene, dep audit
  |-- dependency-review.yml            license allowlist
  |-- docker-smoke.yml                 container contract (paths-filtered)
  |-- CodeQL                                GitHub default setup, not a checked-in file
  |
  '-> pr-readiness.yml  "PR Readiness"  one commit status + one readiness: label
```

Two structural facts explain most of the rest:

- **The merge gate is `PR Readiness`.** Since 2026-10-14 (owner decision) an agent
  squash-merges a PR once `PR Readiness` passes and no check fails; no human
  approval is needed. Individual red checks are strong signals to weigh first.
- **A fork PR is aggregated like any other and can reach a passing readiness
  state**; CodeQL is the one lane it cannot run. See [Fork PRs](#fork-prs).

Out-of-band lanes that never gate a PR:

- **Release and publish**, tag-triggered or manually dispatched: `release.yml`,
  `nightly.yml`, the reusable `build-wheel.yml` / `build-desktop.yml` /
  `build-windows.yml`, `sign-and-notarize.yml`, `publish-cli.yml`,
  `publish-linux.yml`, `publish-docker.yml`, `publish-installer.yml`. The
  marketing site in `site/` is deployed by Vercel from its own project
  settings, not by a workflow; PR coverage for that tree is `site.yml` (npm
  test + production build, no deploy).
- **Verification that is too slow or too expensive for a PR:** `ota-test.yml`
  runs on demand (manual dispatch or a reusable workflow call) and
  builds two real app bundles and performs an actual update swap, because the
  Electron unit suite stops at the `autoUpdater` handoff and never proves a real
  bundle is replaced on disk and relaunches.
- **Maintenance:** `ship-report.yml` (an on-demand summary, dry-run by default),
  `cleanup-temp-screenshots.yml` (prunes the ephemeral `temp-screenshots/` dir,
  see [its README](../../temp-screenshots/README.md); safe because PR bodies
  embed commit-SHA-pinned raw URLs that keep resolving),
  `test-durations.yml` (manual dispatch only: re-measures `.test_durations` so
  pytest-split's shards stay balanced by recorded runtime, and pushes a branch with
  the update; the workflow finishes successfully without creating a PR because
  this repository does not let Actions open one; a maintainer opens or updates it), `issue-triage.yml`
  (a model picks `type:` / `area:` / `platform:` labels from the repository's own
  live label set, because keyword rules mislabel often enough to be worse than no
  label), `issue-summary.yml` (a second, deliberately separate lane posts ONE
  comment per new issue: the report restated for a maintainer, the information
  still missing, and the recent issues most likely to be duplicates. Split from
  triage because publishing prose gives a prompt injection an audience that the
  label path does not have — so this lane, and only this lane, carries the
  markdown neutralizer and the candidate-pool intersection that stop an issue
  body from minting a `#N` reference or a mention. It gets no checkout on
  purpose; grounded, file-level investigation is Issue Radar's Investigate
  button, not a CI comment), `pr-merge-conflict-label.yml` and `fork-pr-label.yml`
  (both mirror a fact GitHub does not surface in the `/pulls` list onto a label), and
  `add-contributor.yml` (a daily cron, plus manual dispatch, adds each merged
  PR's author to the README Contributors block via
  `scripts/update_contributors.py`; because the default branch is protected it
  opens a rolling PR rather than committing directly, like `test-durations.yml`.
  A login in `.github/contributors-optout.txt` is never added, which keeps the
  README's removal promise enforceable against the full-rebuild collector), and
  `agent-os-handoff.yml` (comments the scout / implement / review contract when
  an `agent-os/*` label is applied; it never merges, never checks out the PR,
  and is SHA-pinned).

## Workflow cost controls

In this repository, nightly publishing, the memory benchmark, the macOS OTA test, and
the ship report run only on demand. Their build, test, and publishing steps remain
available; removing the schedules avoids spending on unused nightly outputs.
Tag-triggered releases and PR checks retain their existing triggers. The production
dependency audit keeps its own daily 06:00 UTC schedule so vulnerability-exception
expiry warnings still appear even when no builds are requested.

CI keeps the per-change lanes small. Pull requests and pushes to `main` run the
backend on Python 3.12 on Linux. A weekly CI run (Mondays 05:00 UTC), or a manual
dispatch of CI, adds Python 3.10 and the Windows backend shards. `build.yml` builds
the macOS, Linux arm64, and Windows desktop artifacts only when a desktop-packaging
input changed. Dependabot opens one grouped GitHub Actions update a month.

PR Readiness still updates from workflow and PR events, with an hourly recovery
sweep for missed events. Fork and merge-conflict labels keep their event-driven
updates and run a daily backstop sweep instead of polling throughout the day.

PR/main build artifacts and CI coverage reports expire after one day. A later
retry that needs an expired artifact must rerun its producer. Release build
handoffs retain their existing retention, including the 90-day stable-promotion
record; shortening that record would prevent promotion of tested RC bytes.
Existing artifacts keep their original expiry dates.

## `ci.yml`: correctness

Every job here is blocking.

| Job | What it enforces |
|---|---|
| `scrub-lint` | `scripts/scrub-lint.sh --no-history`. Fails on any internal marker in this public tree, so a sync cannot reintroduce a coupling |
| `vendor-manifest` | `scripts/verify_vendor_manifest.py`. Hashes every file under `src/warding/_vendor` against the committed `scripts/vendor_manifest.sha256` — the tree is excluded from semgrep and the AI reviewers' diff, so this checksum is its only content review. Always-on (not behind the `changes` path filter) |
| `backend-lint` | `isort --check-only`, `flake8`, `mypy` on Python 3.12 for pull requests and pushes to `main` (3.10 and 3.12 on the weekly run), plus `scripts/check_black_formatting.py` — black enforced on every file outside `.github/black-baseline.txt`, which can only shrink — and `scripts/check_subprocess_encoding.py` (self-test first) — no text-mode subprocess call without an explicit `encoding=`, `**UTF8_TEXT`, or a `# subprocess-encoding: locale` marker, outside `.github/subprocess-encoding-baseline.txt`, which can only shrink |
| `harness-parity` | `scripts/check_harness_parity.py`, self-test first. Fails on a newly added line that expresses "this is the Kiro harness" as the absence of another one — a shape that fails toward the permissive answer, so nothing else goes red. Diff-scoped; the whole-tree backlog is a non-failing report |
| `brand-lint` | Two gates, each self-test first. `scripts/check_brand_name.py` is diff-scoped and fails on a newly added line that carries the retired product identity. `scripts/check_company_names.py` is whole-tree and fails on any tracked line that names the retired company name, except the functional identifiers an external system defines (AWS hostnames, package and model ids), which are listed in `scripts/company-name-allowlist.txt`. Both gates allow only the exact original-work attribution lines in root `NOTICE`; they do not exempt the file or permit predecessor branding elsewhere |
| `loop-bound-locks` | `scripts/check_loop_bound_locks.py`, self-test first. Fails on any module-global `asyncio.Lock()`/`Event()`/`Queue()` declaration — those bind to the import-time (or first-use) event loop and raise `RuntimeError` when acquired from another loop (Python 3.10+). The tree uses `warding.loop_lock.LoopBoundLock`; whole-tree, since the backlog is zero |
| `backend-test` | 4 duration-balanced pytest-split shards, `-n auto` within each. Pull requests and pushes to `main` run Python 3.12 only, because the coverage gate reads the 3.12 shard data; the weekly run adds 3.10 (8 jobs), which passes `--no-cov` for a trace-free run. 40-minute job ceiling |
| `backend-test-windows` | windows-latest, 4 shards, `--no-cov`, 180s per-test timeout. Runs only on the weekly run (Mondays 05:00 UTC) or a manual dispatch of CI; pull requests and pushes skip it. The backend supports Windows natively via `platform_compat`, and nothing else in CI holds that line |
| `backend-test-macos` | macos-14, deliberately SCOPED (gateway, socketsec, platform-compat, pod and MCP-apps suites via a glob). A full macOS run needs its own exclusion burn-down first, and a job that is red on arrival trains people to ignore it |
| `backend-test-sandbox` | The one job that clears the AppArmor userns restriction, so the tests guarded by `skipif(not userns_available())` EXECUTE instead of skipping. Runs all eleven sandbox-dependent suites. The shards collect the same files — nothing is deselected — but there the sandbox-guarded tests skip, so this is the only lane where those 85 assertions (the `~/.warding` keystone among them) actually execute |
| `coverage-combine` then `coverage-gate` | Combines the 3.12 shard data, then enforces the project line-rate floors, plus a per-file floor with a shrink-only baseline (all floors live in the job's `env:` block) |
| `frontend-lint` | `tsc -b`, `eslint --max-warnings <measured count>`, `jscpd`, and `npm run i18n:check` |
| `electron-test` | The Electron shell's own node:test suite (`website/electron`) |
| `frontend-test` | `vitest run --coverage` |
| `cfn-lint` | Lints the artifact-deploy templates with a pinned `cfn-lint` |
| `e2e` | The i18n render-time gate, then `python setup.py test_e2e` |

Details worth knowing:

- **The macOS peer-identity canary is asserted by name.** `pytest -q` does not name
  passing tests and a skip exits 0, so a canary that quietly stopped running (a
  changed `skipif`, a collection change) would leave the job green while the gate
  it proves went unverified. The step runs that one node id with `-v` and greps for
  `1 passed`.
- **`backend-test-sandbox` fails loudly rather than skipping.** It clears
  `kernel.apparmor_restrict_unprivileged_userns`, then runs `unshare --mount
  --map-root-user true` as a probe. If the runner image ever stops allowing the
  namespace, the job fails instead of letting the suite silently skip and the gate
  go green having asserted nothing. This is what gives the `hooks.py`
  sensitive-path keystone real CI coverage.
- **`coverage-gate` is fail-closed.** It runs `if: always()` and its first step
  converts any non-success upstream result into an explicit failure, because GitHub
  treats a **skipped** required check as satisfied. It also compares the raw
  line-rate and rounds only for display, so 89.95% cannot pass a 90% floor.
- **`coverage-gate` enforces two different shapes.** The project floors
  (`BACKEND_MIN`, `FRONTEND_MIN`) compare one lane-wide average; the per-file floor
  (`PER_FILE_MIN`, `scripts/check_per_file_coverage.py`) requires *every measured
  file* to clear it. Both are needed because an average is satisfiable without
  touching the files that carry the risk — a well-covered large file pays for a
  bare small one. The per-file gate exempts only the files listed in
  `.github/coverage-baselines/{backend,frontend}.txt`, and that list may only
  shrink: an unlisted file below the floor fails, a listed file that slides further
  fails, and a listed file that *clears* the floor by the same noise band fails
  until it is removed. Refresh with `--update-baseline`, which **prunes only** —
  it cannot add a path or rewrite a recorded rate, so neither a new offender nor a
  regression can be cleared by refreshing instead of by adding tests; seeding a
  new lane is a separate `--seed-baseline`. The floor's rationale and measured
  cost live in the script's docstring, not here, so they cannot go stale in two
  places. Per-file enforcement is skipped for a lane whose suite ran as a
  coverage-free subset, because subset rates are not comparable to a baseline
  recorded on the full suite.
- **`eslint --max-warnings <n>` is a ratchet baseline, and `<n>` is the measured
  count.** Burn it down, never raise it, and never leave it above what
  `npx eslint src/` reports: the difference is a budget new warnings land inside
  without anyone seeing them. `test_eslint_warning_ceiling.py` keeps the number in one place so a
  burn-down cannot leave a stale copy behind.
- **The i18n gates split into three tiers,** and only two can fail: diff-scoped
  zero-tolerance checks (a user-visible literal on a line this branch wrote, a
  file holding more than it did at the base, new English key shape, changed catalog
  values) and whole-repo hard zeros (a `t()` naming a key that does not exist,
  plural concatenation, a stale pseudolocale). Everything else is report-only,
  because a stored whole-repo total is written by whichever branch measured it last,
  so another branch can push it past its number without touching your files and the
  failure then names no diff anyone can fix. Full rules:
  [i18n-gates.md](i18n-gates.md).
- **Every gate that needs a base ref fails rather than skipping when it cannot
  resolve one.** `actions/checkout` fetches depth 1, so
  `.github/scripts/resolve-i18n-base.sh` fetches the one commit and exits non-zero
  if it cannot; a gate that cannot run must fail, not pass.
- **`I18N_BASE_REF` is `pull_request.base.sha`, not `origin/main`.** The base tip is
  a moving target measured at step time while the checked-out tree is a snapshot
  from job start, so anything landing on `main` in between would appear only on the
  base side and be charged to every PR in that window.
- **The e2e gateway boots with `WARDING_STRICT_ON_LOOP_PERSIST=1`**, so an
  un-offloaded session-JSONL mutator that enters the lock on the event loop raises
  and fails the gate at PR time. `WARDING_E2E_REQUIRE=1` turns an
  environment-resolution miss into a hard failure, since a skipped suite would
  otherwise count as a pass having run zero browser specs. Details:
  [e2e-gate.md](e2e-gate.md).

## `build.yml`: the artifacts still build

PR-time proof only, no publishing.

- **`build-wheel`** builds the frontend, stages it into the package, builds the
  wheel, then `pip install dist/*.whl` and `warding --version` as a smoke test.
- **`build-desktop`** builds the Electron app unsigned via `make desktop`, and
  uploads the artifacts. ubuntu-22.04 builds on every pull request and push.
  macos-15, ubuntu-22.04-arm and `build-windows-installer` build only when a
  desktop-packaging input changed (the `desktop-matrix` paths filter). The
  release lane `build-desktop.yml` builds every platform unconditionally.

**Neither desktop lane ever RUNS the bundled backend.** `build-desktop` here and
`build-desktop.yml` in the release lane both build the real `warding-backend`
tree via `packaging/build-desktop.sh` — which provisions a
python-build-standalone interpreter and pip-installs the project into it — and
then only upload the artifact. The wheel lane at least runs `warding --version`.
So a packaging change that breaks the packaged app (a layout change, a launcher
rename, a dependency that fails to install into the bundled interpreter) passes
every gate: the tests that cover packaged-app behavior monkeypatch `sys.frozen`
and `sys.executable`, so they stay green against a simulated environment. The
cheap fix is to run the already-built launcher once in `build-desktop`, the
packaged analogue of the wheel lane's `--version`.

## `code-review.yml`: the deterministic pre-gate

No model, no secrets, so it is safe on forks and always runs. It is the grep-half
of the review rules; the semantic half is left to review, including the
`prepare-pr` skill's local reviewers (see [AI review](#ai-review)).

- **`review-rules`** blocks unambiguous frontend violations on added lines: an
  inline `<svg viewBox>` outside third-party brand-logo components (`*Logo.tsx`;
  Warding's own glyph ships as an asset file, not inline SVG), a
  `<div>`/`<span>` with `onClick` and no `role`, `.innerHTML =`,
  Mermaid `securityLevel: 'loose'`, and an oversized `max-w-[>=900px]` page wrapper.
  It also blocks three backend keystones: a sensitive credential or keystone path
  read that does not go through `is_sensitive_path()`, `denied_commands.json`
  dropping off `security._SENSITIVE_HOME_DIRS` or the governance boot-integrity
  tuple, and a bare `bool()` on an operator-editable boolean opt-out field
  (`bool("false")` is truthy, which would silently disable every protection).
  Advisory warnings, which never fail: unsanitized `dangerouslySetInnerHTML`,
  hardcoded Tailwind colors, new CSS `@keyframes`, sub-10px text.
- **`inclusive-language`** runs a SHA-pinned `woke` over added lines only and fails
  on `(error)` severity. Legacy violations are burned down separately; this stops
  new ones.
- **`sast`** runs Semgrep in a pinned container: first `semgrep --test` over the
  custom rules in `semgrep/` against the annotated fixtures in `semgrep-tests/`
  (both directions — a `ruleid:` line must match, an `ok:` line must not — so a
  rule regression goes red here, not on a later unrelated PR; the rules dir is
  non-hidden because semgrep 1.78's test mode cannot discover tests under a
  hidden directory), then the scan itself, diff-only against the base,
  community packs plus `semgrep/`, with `--error`. The fixtures are listed in
  `.semgrepignore` so the deliberately vulnerable fixture code is never read by
  the scan. Blocking.
- **`dep-audit`** calls the reusable `dependency-vulnerability.yml`, which runs
  `scripts/check_npm_audit.py` over every lockfile-backed Node project and fails
  closed on **high or critical production** vulnerabilities. Time-boxed exceptions
  live in `.vulnerability-exceptions.json`.
- **`pr-hygiene`** enforces a Conventional-Commits PR title (it becomes the
  squash-merge message) and at most two commits (`git rev-list --count <= 2`).
  One commit stays the norm; the second is there so a mechanical follow-up (a
  regenerated artifact, a formatting sweep) can stay separable from the change
  it accompanies. Both blocking.

Separately, **`dependency-review.yml`** fails a PR that adds or changes a
dependency whose license is off the curated allowlist in
`.github/dependency-review-config.yml`. A maintainer can bypass it for the commit
they reviewed with the `license-override` label, honored **only** on the `labeled`
event, so a later push arrives as `synchronize` and re-runs the gate; a new,
unvetted dependency cannot ride in on a stale override. The action needs the
repository's dependency graph (GitHub Advanced Security on a private repo). When
that product feature is unavailable the job probes `/dependency-graph/sbom`
first and **skips** rather than failing closed on "not supported on this
repository" — a missing scanner is not a license hit. Enable the graph to
restore the gate.

**`docker-smoke.yml`** is paths-filtered to the container surface (`docker/**` plus
the three source files the container contract spans: the bind override in
`dashboard/origin.py`, the probe Host-barrier exemption in `dashboard/server.py`,
and the liveness payload in `dashboard/handlers/core.py`). It builds the image from
a locally-built wheel and proves, across a real container boundary, that
`WARDING_BIND=0.0.0.0` makes the gateway reachable from the host, that token auth
still guards the API on that non-loopback path, that `/api/health` works (the image
HEALTHCHECK depends on it), that kiro-cli runs inside the image, and that channel
credentials passed as container env are moved into the data home's `.env` and
scrubbed from every long-lived process environ.

## AI review

No AI reviewer runs in CI, and `PR Readiness` waits on none. AI review happens
before a push, in the `prepare-pr` skill's local review gate: the bundled Warding
profile dispatches two read-only reviewers on different models through the
operator's own harness, and each applies a review contract kept in
`.github/review-prompts/`:

| Reviewer | Contract | Shape | Reads |
|---|---|---|---|
| `gpt` | `gpt-diff-not-evidence.md`, `gpt-review-core.md`, `gpt-output-contract.md`, then `gpt-falsification-mandate.md` + `gpt-falsification-verdict.md` | Two separate calls: discovery, then an authoritative falsification call | The diff, the code, and the PR title and body as **UNTRUSTED** context |
| `opus` | `opus-discovery.md`, then `opus-validate.md` | Two separate calls: discovery, then validation | **Code only**: the diff and the code, never PR prose or comment threads |

Every contract and the review rule files are read from the PR's **base** commit,
so a change cannot weaken the reviewer or the rules that judge it. The reviewers'
findings are fixed or answered before the push; nothing about them reaches CI.

### One binary contract

Both contracts share one rule: severity encodes exactly one thing, *does this
block the merge*, **never confidence**. There is no "possible issue" tier. A
finding must state a concrete input or condition that occurs in practice, the call
path to the changed line, and an observable wrong outcome; anything phrased as
"could", "might" or "if a caller were to" is **not a finding**, and silence is the
correct output. Only two labels exist: **BLOCKING** (on the closed WHAT BLOCKS
list) and **FINDING** (advisory, never blocks). The calibration note says
"No findings." is the expected output for a typical PR. Diff text is never
evidence: a comment claiming code is broken cannot ground a finding.

### Asymmetric multi-pass is intentional

Both reviewers run a discovery pass that generates candidates, then a pass whose
primary job is to *kill* them. The `opus` discovery stage carries no precision
gates at all, because a prompt asked to discover AND to police its own precision
stops discovering; its validation stage applies a confidence floor and the closed
blocking list. A candidate survives only if the second pass re-derived the input,
the call path and the observable outcome itself from code it opened. The second
pass may also *add* a defect discovery missed, but only under that same grounding,
and such a finding is tagged `(origin: validation)`, because it is un-falsified by
construction: the tag is what lets a reader weight it accordingly.

## `pr-readiness.yml`: the aggregator

It executes no tests. It resolves the PR's current head SHA, **drops stale events**,
queries the latest run per monitored workflow, and publishes **one `PR Readiness`
commit status plus one `readiness:` label**.

- **Always required:** CI, Build, Code Review.
- **Additionally required on a same-repo PR:** CodeQL.
- **CodeQL is not a checked-in workflow.** It runs via GitHub default setup and is
  resolved by `path == "dynamic/github-code-scanning/codeql"`. `skipped` counts as
  passed for it.
- **Labels:** `readiness: checking` (pending), `readiness: action required` (a
  blocker), `readiness: passed`. Exactly one is ever present.

Two subtleties:

- **It refreshes while a workflow is re-running, but not when one starts.** It triggers
  on `workflow_run` `in_progress` and `completed`, not on `requested`. `in_progress` is a
  merge guard, not a cosmetic: it is the only type that sees a monitored workflow go back
  to running, because a re-run reuses the same run and increments its attempt instead of
  creating a new one. Without it, a re-run of an already-green lane would leave readiness
  publishing the pre-re-run `success` for the whole re-run -- and since that status is the
  branch-protection handle for the entire fan-out, armed auto-merge could merge a revision
  whose lane is failing at that moment. `requested` is the type that carries nothing: it
  fires at run CREATION, when no lane can have a verdict yet and readiness has already
  published `checking` from the `pull_request_target` path. Since every type fires once per
  monitored workflow per revision, each listed type adds one readiness run per monitored
  workflow to every head update. The `pr+sha` concurrency group collapses the burst for
  execution, but a collapsed run has already consumed its dispatch slot, so the group does
  not bound that cost.
- **A `pull_request_target` run gets its own isolated concurrency group.** Those are
  the only readiness runs that surface as a CheckRun in the PR's rollup, and GitHub
  marks any superseded run "cancelled" whichever way `cancel-in-progress` is set, so
  sharing a cancelling group would show a spurious cancelled check on the PR even
  though the authoritative commit status is fine. Un-collapsed runs on superseded
  revisions simply no-op green, because the evaluate and publish steps are idempotent
  and stale-SHA guarded. The `workflow_run` and `workflow_dispatch` runs do not appear
  in the rollup, so they keep the cheap per-`(pr, sha)` burst collapse.
- **The pending sentinel is conditional.** A `pull_request_target` open/synchronize
  run is meant to surface a transient "checking" signal, but it can be
  runner-queue-delayed past the `workflow_run` runs that already published the
  terminal verdict for the same SHA. Adding the sentinel unconditionally would then
  clobber a decided verdict back to `checking` with no further event left to
  recompute it on an unchanged commit, freezing the status at pending indefinitely.
  So it is added only when the live evaluation still found something genuinely
  incomplete.
- **A transport error during evaluation is non-terminal.** Every read-only `gh`
  call goes through a bounded retry helper (3 attempts with backoff, 120s cap per
  attempt); a non-429 HTTP 4xx is treated as permanent misconfiguration and fails
  the job loudly instead of retrying. If an **evaluation** read still fails after
  the retries, the evaluate step publishes an explicit non-terminal "could not be
  evaluated" verdict (`pending` under `readiness: checking`) instead of exiting
  non-zero — so a transient network/TLS blip during evaluation never leaves a red
  check-run or skips the publish step (the same commit once evaluated
  green then red 39 seconds apart). Exhausted retries in the other steps (context
  resolution, closed-PR label cleanup, the publish step's own reads) still fail
  the job — only the evaluation loop has the non-terminal branch. This does not
  weaken the gate: `pending` blocks merge exactly like `failure`, and only a
  transport error with no already-observed blocker takes that branch (a genuine
  failure recorded by an earlier lane dominates and the verdict stays the
  terminal red `action required`, with a summary note that the evaluation was
  truncated). Recovery is automatic — the self-heal sweep re-fires stale pending
  statuses, and any later monitored-workflow event recomputes sooner. A truncated
  run defers (publishes nothing) only when the revision already carries a
  **blocking** verdict — the merge is already held and pending would only discard
  the red's diagnostics. Every other prior state publishes pending: an existing
  *success* is re-pended (a rerun means validation state is unknown again, and a
  stale green left mergeable is the unsafe direction — pending can only ever
  block, never allow), and an unreadable verdict state gets the same fail-safe
  treatment. The status
  POST itself is never retried: commit statuses are last-write-wins with no
  conditional write, so any retry races a concurrent run's newer verdict — a
  failed POST fails the step loud and a re-run republishes. The label writes
  keep only the narrow 404/already-exists race tolerance they already have.
- **Nothing keys off `workflow_run.pull_requests`.** That array is empty whenever the
  head repository is a fork. The job gate admits every `pull_request` and `dynamic` run and lets the
  head SHA resolve to a PR via `repos/:repo/commits/:sha/pulls`, and a monitored run is
  bound back to the PR by `(head_repository.full_name, head_branch)` on top of the
  `head_sha=` query — a pair that is populated on a fork run, and unique because only
  one open PR can exist per source repository + branch. Keying either place on the PR
  number froze a fork PR at pending forever: the gate skipped every re-evaluation, so
  the verdict was whatever the `pull_request_target` run saw *before* the monitored
  workflows existed, and the lookup independently reported already-green workflows as
  `(not started)`.

## Fork PRs

A fork PR gets no repository OIDC credentials or secrets. No PR lane needs them, so
every lane runs on a fork PR except CodeQL: this repository's managed default-setup
CodeQL workflow is not scheduled for fork heads. **A fork PR can still reach
`readiness: passed`**: `pr-readiness.yml` reports CodeQL as a non-blocking "Not
eligible" note rather than a blocker, so readiness says the same thing on a fork as
anywhere else: the eligible automated validation passed for this revision. Human
approval and branch protection remain separate gates.

**`fork-workflow-guard.yml`** blocks a fork PR that modifies anything under
`.github/**`, the vector a fork would use to fake basic-CI results (rewrite `ci.yml`
to pass) or tamper with CODEOWNERS. It is deterministic on purpose: "does the diff
touch `.github/**`" is a file-path check, so a grep on the authentic changed-file
list is completely reliable, instant and free, where a model gate would be slower,
cost money and could hallucinate. It runs from the default branch (via `workflow_run`
of CI, plus `pull_request_target` for the override-label re-evaluation), so a fork
cannot disable it, and a fork's own `pull_request` runs have no `checks: write` to
forge its verdict. A maintainer who has reviewed a legitimate workflow change applies
the `allow-fork-workflow-change` label and the guard re-evaluates green; the label is
stripped on a new revision, so the override cannot carry over.

## Over-engineering resistance

AI-native coding skews toward over-engineering, and a naive AI reviewer compounds it
by demanding still more mechanisms, which produces unending review loops. Every layer
resists this:

- **Both review contracts share an identical FIX BAR:** every finding must carry a fix
  expressible as an edit to lines **this PR changed**. If the fix would need a new
  function, module, abstraction, config knob, dependency, or an edit to untouched
  code, it is out of scope for the reviewer. The `gpt` contract drops such a finding;
  the `opus` contract **demotes it to advisory instead of dropping it** -- the author cannot land the
  remedy in this PR, so it must not gate the merge, but the signal is real and a
  human decides. A regression the diff itself introduces still blocks either way,
  since reverting the hunk is an in-diff fix. **The absence of a
  mechanism is never a finding.** This makes "add mechanism X" structurally
  un-reportable: the demand fails the bar before it can become a finding. A scope cap
  complements it: the `opus` reviewer stays within the evident scope of the diff (it is
  code-only).
- **The WHAT BLOCKS list is closed:** exhaustive, never extended, never reasoned about
  by analogy, with no "and other serious issues" clause. A finding blocks only if it
  is a `blocking: true` review rule violation on a changed file (or this PR
  weakening such a rule), or a **reachable and concrete** residual-class defect: a
  security hole with a named trigger, a crash or data loss or corruption on a path
  this diff changes, or a removed guard with no compensating replacement. Style,
  naming, speculative performance and hypotheticals never block.
- **`prepare-pr`'s severity gate closes the loop:** validate each finding's
  legitimacy first, fix the true Critical and High ones, **rebut a false positive with
  evidence rather than appeasing it by changing correct code**, and defer the low ones.
  Combined with the single-commit rule and description reconciliation, that keeps a PR
  converging on its stated purpose instead of accreting scope round over round.

The net effect: expensive or irreversible risk blocks, and everything else is advice a
human can take or defer. "More mechanism" is deliberately not a demand that can block.
