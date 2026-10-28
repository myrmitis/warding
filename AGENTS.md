# Rules for AI Assistants

**This file is a ROUTER, not a manual.** It carries only the rules whose violation
causes damage before a pointer could be read. Everything else is a link you MUST
open before touching that subsystem: see
[Read before you touch](#read-before-you-touch). The frontend has its own router,
[`website/AGENTS.md`](website/AGENTS.md).

**Product overlay:** this checkout is **Warding** (`myrmitis/warding`).
Read [`WARDING.md`](WARDING.md) (the overlay, with the NO-SAY list) and
[`WORKING_BRIEF.md`](WORKING_BRIEF.md) before any product, brand, CLI, or
model-catalog change. Product / architecture / roadmap overlays:
[`PRODUCT.md`](PRODUCT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
[`ROADMAP.md`](ROADMAP.md). The package, CLI, data home and environment prefix
all carry the product name (`warding`, `~/.warding`, `WARDING_*`).

**Progress and memory:** GitHub issues own status for bugs, features, and
stories; ADRs ([`docs/adr/`](docs/adr/README.md)) own the *why*;
[`docs/TASK_MAP.md`](docs/TASK_MAP.md) is a dated local handoff for work in
flight. The task map carries the session start/finish steps; the operator's
`~/dev/memory/INDEX.md` is a reference, not authority. Record work in place —
commit and push only when explicitly authorized.

## What this is

Warding runs coding agents on the operator's own machine, under a policy
the agent cannot read or rewrite. Chat sessions run the one harness the
operator chooses in one setting (`agent.acp_backend`); spawned subagents can
be routed to another installed harness by the harness router (flat-rate
quota before metered, task kind, cooldown after a usage limit or failed
login), which picks a harness and never forwards provider traffic. Chat from
the web dashboard, the CLI, or a messaging channel; run multi-step tasks
unattended; schedule cron jobs; keep memory across sessions. It drives an
LLM through an ACP adapter plus MCP tools. `kiro-cli` is optional. A model
catalog on loopback lists names and forwards nothing.

- **Backend:** Python package `warding` in `src/warding/`.
- **Frontend:** React + TS + Vite SPA in `website/`; the built `dist/` is staged
  into `src/warding/static/dist/` and served by the backend.
- **Data home:** `~/.warding`, overridden with `WARDING_HOME`. There is no
  other data home and no fallback to another product's directory.
- **Distribution:** public GitHub, plain setuptools, public PyPI / public npm.
- **CLI:** `warding`, the one console script.

Full map: [`docs/architecture/overview.md`](docs/architecture/overview.md).

## Read before you touch

Load the doc for the row you are working in **before** you change code. Update it
in the **same commit** when you change what it documents.

| If you are touching… | Read first |
|---|---|
| `platform/`, editions, CPP seam, governance | [platform-context](docs/system-specs/modules/platform-context.md) + [governance](docs/system-specs/modules/governance.md) |
| `security.py`, `hooks.py`, denied commands, sensitive paths | [security](docs/system-specs/modules/security.md) + [sel](docs/system-specs/modules/sel.md) |
| the security model as a whole, threat boundaries | [security-deep-dive](docs/architecture/security-deep-dive.md) |
| `computer_use/` | [computer-use](docs/system-specs/modules/computer-use.md) |
| `acp/`, kiro-cli transport, providers | [acp-client](docs/system-specs/modules/acp-client.md) + [providers](docs/system-specs/modules/providers.md) |
| `model_router/`, built-in catalog (no provider forwarding) | [model-router](docs/system-specs/modules/model-router.md) |
| `harness_router/`, `routing.json`, routed `spawn_run`, `warding route` | [harness-router](docs/system-specs/modules/harness-router.md) + [harness-parity](docs/system-specs/modules/harness-parity.md) |
| the product overlay (`WARDING.md`), product identity, the thesis | [`WARDING.md`](WARDING.md) + [`WORKING_BRIEF.md`](WORKING_BRIEF.md) + [`PRODUCT.md`](PRODUCT.md) |
| adding or adapting an agent harness (BYO, KAS, claude seam) | [harness-parity](docs/system-specs/modules/harness-parity.md) (invariants) + [harness-parity-gate](docs/ci/harness-parity-gate.md) (CI) |
| sessions, slots, session keys, PIDs | [session](docs/system-specs/modules/session.md) + [history](docs/system-specs/modules/history.md) |
| session summaries, the chat summary panel, intent extraction | [session-summary](docs/system-specs/modules/session-summary.md) |
| memory, embeddings, vectors, lessons, skills, hooks | [memory-skills-hooks](docs/system-specs/modules/memory-skills-hooks.md) |
| MCP servers or tools (adding, changing, statelessness) | [mcp](docs/architecture/mcp.md) |
| apps, App Kit, manifests, app agents | [app-kit-platform](docs/system-specs/modules/app-kit-platform.md) + [app-kit/](docs/app-kit/README.md) |
| artifacts, companion chat | [artifacts](docs/system-specs/modules/artifacts.md) |
| cron, learn, dashboard handlers | [learn-cron-dashboard](docs/system-specs/modules/learn-cron-dashboard.md) |
| Slack, Discord, any channel, messaging, approvals | [messaging](docs/system-specs/modules/messaging.md) + [slack-gateway](docs/system-specs/modules/slack-gateway.md) |
| subagents, spawn, orphan recovery | [subagent](docs/system-specs/modules/subagent.md) |
| task runner | [task](docs/system-specs/modules/task.md) + [taskrunner](docs/system-specs/modules/taskrunner.md) |
| `workflows/` (the dynamic-workflow engine) | [workflows](docs/system-specs/modules/workflows.md) + [workflow-gates](docs/system-specs/modules/workflow-gates.md) |
| themes | [themes](docs/system-specs/modules/themes.md) + [theming-contract](website/docs/theming-contract.md) |
| anything under `website/` | [`website/AGENTS.md`](website/AGENTS.md) |
| user-facing strings, dates, numbers, sort order | [i18n-catalog](website/docs/i18n-catalog.md) (authoring) + [i18n-gates](docs/ci/i18n-gates.md) (CI) |
| tests: flakes, speed, fixtures, sharding, side effects, conftest isolation | [testing-conventions](docs/system-specs/common/testing-conventions.md) + the [writing-tests](src/warding/builtin_skills/warding-dev/writing-tests/SKILL.md) skill |
| browser E2E | [e2e-gate](docs/ci/e2e-gate.md) |
| CI, PR flow, review gates | [ci-and-reviews](docs/ci/ci-and-reviews.md) + [CONTRIBUTING.md](CONTRIBUTING.md) |
| constants, magic numbers, where a limit lives | [code-style](docs/system-specs/common/code-style.md) |
| injected `[Cron notification]` / `[Subagent completion event]` | [injected-messages](docs/system-specs/common/injected-messages.md) |
| build, install, dev mode | [CONTRIBUTING.md](CONTRIBUTING.md) + [install](docs/guides/install.md) |
| Windows / cross-platform process, signal, lock, metrics | [windows-install](docs/guides/windows-install.md) + the shim table below |
| a release, or `CHANGELOG.md` | [release](docs/build/release.md) |
| errors, retries, user-facing failure text | [error-handling](docs/system-specs/common/error-handling.md) |

The whole doc tree is indexed from [`docs/README.md`](docs/README.md). User-facing
docs that ship in the package live in `src/warding/docs/` and are indexed by
[its README](src/warding/docs/README.md).

## Never re-introduce (scrubbed internals)

This repo is a public OSS tree. Never re-add:

- **Build/infra:** vendor-internal build systems, reviewer-routing files and
  private package registries. setuptools + public PyPI / public npm only.
- **Services/auth:** vendor-specific SSO or federated login, managed tunnels,
  hosted telemetry ids, and integrations with private MCP, ticketing or
  document services.
- **Keep the tunnel seam inert.** `tunnel/manager.py` delegates to the
  `TunnelProvider` seam, whose public Default is a no-op: this build never exposes
  the dashboard through a managed tunnel. Do not add a real tunnel provider here.
- **Other providers.** Warding's `agent.provider` stays `enum=["acp"]`.
  `kiro-cli` is optional. Keep the dormant `ACP_BACKEND_CLAUDE` /
  `_is_claude` seam in `acp/client.py` so a companion package can re-register
  Claude Code; do NOT re-add the public registration glue. A harness added at
  `agent.acp_backend` is a different question and is governed by
  [Harness parity](#harness-parity-runtime-selection-and-capability-boundaries) —
  adapted, never a second `agent.provider` value.
- **OSS-flipped defaults:** always-on in-process embeddings, Piper TTS by default,
  a default-open Slack enterprise gate, lazy STT extras.
- **Removed surfaces:** the Channels app is hidden from the App Store and the
  Board app is removed. Do not restore them.
- **The retired identity.** Apart from the exact original-work attribution in root `NOTICE`, none of
  the retired product's name, data homes,
  env prefix, CLI aliases, bundle ids, download or update hosts, repository
  slug, or ghost mascot ship in Warding. Warding's own identity (the Ward
  Seal mark, the paper-and-night palette, Fraunces and IBM Plex Sans) is
  generated from [`assets/brand/build.py`](assets/brand/build.py); change it
  there, not by hand-editing a raster.
- **The predecessor project's identity.** Warding was first developed under a
  predecessor name. Its domain, repository slug, environment prefix, data home,
  package and bundle id do not ship. `scripts/check_predecessor_name.py` fails
  any tracked line that spells them, outside `docs/adr/` and `CHANGELOG.md`.
  A Windows directory junction keeps its name; the gate does not match that term.
- **The retired company name.** Prose, comments, docs and UI text name
  the service or the distro (S3, Polly, AL2023), never the company.
  `scripts/check_company_names.py` fails any tracked line that names it, except
  the functional identifiers an external system defines and the code must spell
  exactly (AWS hostnames, package and model ids, kiro-cli's own file names),
  which are listed in `scripts/company-name-allowlist.txt`. The two exact
  original-work company-attribution lines in root `NOTICE` are also allowed
  under Apache-2.0 section 4(d); this does not permit branding elsewhere. Run it before
  pushing; add an allowlist entry only with a reason in the PR.

`scripts/scrub-lint.sh` gates `src/`, `website/src/`, `scripts/`, `config/`,
`packaging/`, and the top level; keep `docs/` clean by convention. Rationale for
what was removed: [post-launch-removals](docs/system-specs/post-launch-removals.md).

**Keep** the generic security controls: AKIA/ASIA credential redaction,
destructive-command deny rules, `~/.aws` / `~/.ssh` path blocking, the SEL audit log.

## Security invariants (do NOT weaken)

- **Keystone.** `security_policy.json`, `profiles/`, `admission_policy.json`, and
  `computer_use.json` under the data home are in `security._SENSITIVE_HOME_DIRS`,
  so the agent can neither read nor write its own ceiling. When editing
  `security.py`'s sensitive-path or bash-command matchers, keep these covered,
  including write and extract verbs. This single mechanism is what makes the
  ceiling un-disableable.
- **Governance.** `effective = POLICY ∩ PROFILE`, tightest-wins, enforced at
  Warding's OWN PreToolUse gate: it denies a tool or MCP call even when the kiro
  agent config granted it. The evaluator is scope-name-agnostic, so adding a scope
  is a `SCOPE_CATALOG` data change, never an evaluator edit.
- **`CONTRACT_VERSION` stays pinned at 1 pre-launch.**
- **Denied commands** are `DeniedCommandRule` records (`BUILTIN_DENIED_RULES`)
  enforced only at the `hooks.py` PreToolUse gate. Never restate the rule count in
  prose: `test/test_denied_commands_security.py` pins it, and a restated count goes
  stale silently.
- **Computer use is deliberately NOT governed.** It is one operator opt-in on the
  keystone `computer_use.json`. Do not add `computer_use.*` scopes, capability
  rows, approval ordinals, or pointer permits. Its refusals run **in band** on the
  `tools._dispatch` path, never at the fail-OPEN `hooks` gate, because a
  pre-authorized tool can skip that gate. Keep them there. Secure-field redaction
  is an always-on floor with no policy key. `click_method: "auto"` must NEVER
  resolve onto `"global"`: that is the only thing between an ordinary click and the
  operator's real cursor.

## Model selection

Never hardcode a model id (`claude-*`, `opus*`, `sonnet*`, `haiku*`, `gpt-*`,
`fable*`) as a default or fallback. Accounts differ in entitlement and even
`"auto"` is not served in every partition, so a hardcoded id fails at runtime
(silent until the first prompt) for anyone not entitled to it.

- **Default is `"auto"`** (`agent.model` / `config/defaults.json`) — don't replace
  it with a concrete model. `"auto"` is validated like any other id; it is not
  assumed usable.
- **Resolve, don't guess.** For a model chosen on the caller's behalf (background
  one-liners, tips, inherited/cold-start applies) route through
  `acp.client.resolve_usable_model(preferred, advertised)`: send a served id; send
  `"auto"` only when advertised; otherwise return `""` = **inherit the session's
  served backend default**. `run_bg_oneliner` adds a one-shot reactive retry on a
  wire rejection as a backstop. An **explicit user pick** is the opposite — it
  `raise`s `AcpModelUnavailable`; never silently swap a model the user chose.
- **Pickers** MUST list options from `GET /api/models` (the advertised set), never
  a static in-code list.
- **Pin a cheaper model** only via `agent.role_models.<role>` (`background`,
  `subagent`) → `AgentConfig.resolve_model(role)`; roles default to `"auto"` and
  never inherit `agent.model`.
- **Entitlement check:** always the shared predicate
  `acp.client.model_is_unusable(id, advertised)` (with `advertised_model_ids(...)`);
  an empty/unknown advertised set means "allow". Never hand-roll a membership test.
- The `claude_code` seam's `cc_model` (`_BACKGROUND_CC_MODEL`) is the one allowed
  concrete fallback (that backend can't resolve `"auto"`); keep it off the default path.

`code-review.yml` fails on a newly added hardcoded model literal outside
`model_registry*`, the config schema, and tests.

## Harness parity: runtime selection and capability boundaries

Never express "this is the Kiro harness" as the ABSENCE of another harness.
Warding defaults to `auto` through the runtime registry; kiro-cli is optional
and last in installed-runtime selection. Its established transport and capability
boundaries remain explicit (`ACP_BACKEND_KIRO`, spelled `""`), as do those of
the other adapted harnesses (the dormant `ACP_BACKEND_CLAUDE` seam, KAS, and
any bring-your-own harness). A negative test like `not is_claude_backend` reads
correctly with two harnesses and then silently hands the third a capability, a
sandbox waiver, or a session label nobody granted it — and it fails toward the
permissive answer, so nothing goes red until an operator who never opted into
that harness pays for it.

- **An added harness ADAPTS, it does not widen.** It may only fit itself to the
  seams the Kiro harness already runs through: no new conditional, required
  argument, awaited step, or failure mode on the Kiro path, and no collapsing a
  per-harness literal (spawn argv, `PROTOCOL_VERSION`, client capabilities) into
  one form every harness accepts. A harness that cannot land without changing the
  Kiro path does not land yet.
- **Identity is positive.** `is_kiro_backend` / `== ACP_BACKEND_KIRO`, or
  membership in a named `ACP_BACKENDS_*` set in `acp/types.py`. Never a bare
  string literal, an inequality, or a negation.
- **Capabilities are opt-in membership sets** (`ACP_BACKENDS_SESSION_SHARING`,
  `ACP_BACKENDS_STEER`, `ACP_BACKENDS_INTERNAL_SANDBOX`,
  `ACP_BACKENDS_MANAGED_MCP`), and every harness's membership is an explicit
  decision. `is_kiro_cli` is the one that fails OPEN: it makes
  `sandbox.wrap_argv` SKIP Warding's own seatbelt in favour of the harness's
  internal sandbox, so granting it to a harness without one leaves the agent
  process unconfined.
- **Warding defaults to auto.** `agent.acp_backend` defaults to `ACP_BACKEND_AUTO`;
  an unusable persisted value normalizes to `auto` with a logged reason. The
  runtime registry chooses the first installed runtime, with optional kiro-cli
  last. `ACP_BACKEND_KIRO` remains selectable; its capability and sandbox rules
  stay intact. A disabled `kiro` lane in `routing.json` excludes routed work,
  not chat selection. Pin `agent.acp_backend` to an installed, authenticated
  harness when chat must exclude Kiro. `agent.provider` stays `enum=["acp"]`.
- **Registration is additive at the seam** — `platform/interfaces.py`'s
  `ProviderRegistry`, a v1 addition with no `CONTRACT_VERSION` bump. A new
  provider capability lands on the `LLMProvider` ABC with a safe default, never
  as a `hasattr` probe on the Kiro path.
- Invariant ids, and the test pinning each, are in
  [harness-parity](docs/system-specs/modules/harness-parity.md). Cite them bare
  (`H7`) in code comments and review findings.

`scripts/check_harness_parity.py` fails on a newly added negative identity test
under `src/warding/` (run it locally with
`HARNESS_BASE_REF=origin/main python3 scripts/check_harness_parity.py`); the
judgment half is the `harness-parity` rule in `REVIEW_RULES.yaml`.

## Specification management

- MUST read the relevant spec under `docs/system-specs/modules/` before changing
  the code it covers.
- MUST update the spec in the SAME commit when an API, schema, or documented
  behavior changes.
- MUST add the doc to its directory `README.md` when creating one, and MUST update
  every index that points at a doc you move, rename, or delete. `scripts/docs-lint.sh`
  enforces this; run it before you commit a docs change.
- MUST NOT create additional markdown files unless explicitly instructed.
- Task specs go in `docs/task-specs/YYYY/MM/${task-id}/`. Treat `docs/task-specs/`
  as an archive, never as current context.

## Git

- Do NOT proactively `git commit`. Commit only when asked.
- Do NOT `git push` unless the user explicitly says to push. Being asked to commit
  is NOT permission to push.
- `main` is the default branch; changes land through a GitHub PR. Full flow:
  [CONTRIBUTING.md](CONTRIBUTING.md).
- **Merges (owner decision, 2026-10-14):** agents may squash-merge a PR once
  `PR Readiness` passes and no check fails. The owner does not review each PR.
  Do not approve your own PR, and never push to `main` directly.

```
<type>: <summary — max 72 chars, imperative, lowercase, no period>

<body — what and why, not how; wrapped at 72>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `revert`.
One logical change per commit.

## Release Changelog

> **Releasing or promoting a version? Read `docs/build/release.md` first.** It is
> the authority on the channel model, version stamping, and the **RC → stable
> promotion runbook** — including why anything a stable user will see (a clean
> version number, a finalized changelog) must be baked into the RC bytes *before
> the RC is cut*, since promotion never rebuilds. This section covers only the
> changelog rules.

`CHANGELOG.md` is written **only when a version is bumped**, and everything
already in it is immutable. Two halves enforce that: the
`changelog-is-written-at-version-bump-only` rule in `REVIEW_RULES.yaml` applies the
judgment a reviewer has to make (is this a commit dump? should this PR be touching
the file at all?), and `scripts/check_changelog_history.py` enforces what needs no
reading — every section the base documents as shipped survives byte-identical, and
the file contains **only** shipped sections. The parser that renders it is
`src/warding/changelog.py`.

- **Your feature PR does not touch `CHANGELOG.md`.** The release PR writes the
  section covering everything that shipped. A per-PR changelog line is how the
  file grows into something nobody reads, and how it acquires an `## [Unreleased]`
  section that then has to be untangled at release time. The commit subject is
  the record until a bump names it.
- **There is no `## [Unreleased]` section, and the gate refuses one.** To see what
  is pending, read `git log --oneline <last-tag>..HEAD`. With shipped sections
  frozen, that leaves exactly one legal shape for a changelog diff — prepend one new
  section — because there is nowhere to append a per-PR line to.
- **One section per release, newest first**, headed exactly
  `## [X.Y.Z] — YYYY-MM-DD`. Never a prerelease spelling: `0.3.0-insider.9` and
  `0.3.0-rc.2` are drafts of `0.3.0`, are folded onto it by the parser, and must
  not get their own heading. The gate refuses those too, so a release branch writes
  its section once, under the release's final heading, rather than carrying a draft
  it renames later.

- **Never delete or edit a shipped section.** A release PR prepends one section
  and leaves every earlier one byte-identical.

Format:

- A two-to-four line opening paragraph naming the release's theme. Not a count of
  commits.
- Then `###` subsections grouped by **what the reader gets**, ordered most
  interesting first. Never group by commit type: nobody opens a changelog looking
  for the refactors.
- Each bullet is `- **Short name** — what the user can now do`, one or two lines,
  in plain language and the present tense.
- Describe the capability, not the mechanism. No commit hashes, PR numbers, file
  paths, module names, or internal vocabulary.
- **Never generate the section from a commit dump.** A list of commit subjects, a
  `Bug Fixes (88 total)` header, or a trailing `and 65 more (see commit log)` is
  the failure mode this format exists to prevent. Fixes that are invisible to the
  reader are simply left out; fixes that are visible are described as an outcome
  and folded into the subsection they belong to.
- **Name the breaking changes first.** A `### Before you upgrade` section leads
  when the release removes a capability, raises a floor (a minimum Node or Python
  version), changes a default, or alters behaviour a user has configured around.
  This is the part of a changelog with no substitute: a reader can discover a new
  feature later, but a withdrawn one costs them an outage.
- **A closing `### Notable fixes` section is allowed, and is not a commit dump.**
  It exists so a reader can check whether their particular annoyance is gone,
  written as what is now true ("Teams retries a rate-limited message instead of
  dropping it"). Past roughly twenty items, group them by area into short prose
  paragraphs under a bolded lead rather than a flat bullet list — eighty bullets
  is a wall nobody scans. What makes it a dump instead is a total count, a bare
  commit subject, a scope prefix, or an "and N more" tail; it carries none of
  those, and a fix nobody would notice does not earn a line.
- **The split, not a line budget, is what keeps it readable.** The showcase body
  carries new surfaces, new capabilities, and perceptible performance changes;
  everything fix-shaped goes to the grouped tail. A body growing past the
  previous release's is a signal to move items into the tail or group them
  harder — not a licence to keep adding, and not a reason to drop a real change.
  A release covering substantially more shipped work will be longer, and that is
  correct; an unedited one is not.
- **Verify coverage against the commit range, not against your memory of it.**
  Partition `git log <last-tag>..HEAD` and account for every commit, because the
  omissions are systematic rather than random: a change whose subject names one
  subsystem while touching a shared surface is exactly what a keyword or path
  scan misses, and nothing downstream ever reports it. It is also systematically
  biased *against* the release's headline: the PR that lands a large surface is
  the least likely to have spent effort on a changelog line, so an accumulated
  file over-represents small fixes and omits the features people upgraded for.
- **The section ends with `### Contributors`**, crediting everyone whose code
  shipped in it — `@handle`, alphabetical by username case-insensitively, bots
  left out. Derive it from the release's own range rather than by hand:
  `gh api repos/myrmitis/warding/releases/generate-notes -f tag_name=<tag>
  -f previous_tag_name=<last-tag>` names the author of every merged PR, so nobody
  is dropped for having a quiet commit subject. **This belongs to the changelog
  only.** A GitHub Release page renders its own contributor block from the tag
  range, natively, whatever its body says — so putting a list in the release notes
  duplicates it on the page, immediately above GitHub's own. The changelog needs
  its own because that copy is what ships inside the wheel and what the
  dashboard's Releases page reads, where no such block exists.

## Testing policy: E2E over unit

Owner policy (2026-10-16, shared in `~/.agents/AGENTS.md`): do not add unit or
integration tests on your own initiative, and no TDD unless asked. Prove a
change by driving the product the way a user does.

- New coverage goes to the E2E layer: `python setup.py test_e2e` (the
  [e2e-gate](docs/ci/e2e-gate.md): real gateway, fake backend, Playwright
  dashboard suite). A user-visible change to the CLI, gateway or dashboard
  extends that suite, not `test/test_*.py`.
- Existing pytest coverage stays and must pass (`python -m pytest`, below).
  Never delete, skip, weaken or `xfail` a test to go green; if one is wrong,
  say so and stop. Tests that pin security invariants (above) are a contract.
- Exception, ask first: pure logic with a clear spec (policy intersection,
  parsers, model-registry resolution). When the owner asks for a test at any
  level, write exactly that; the `writing-tests` skill then governs how.

## The gate before you commit

```bash
python3 scripts/check_black_formatting.py && python3 scripts/check_subprocess_encoding.py && isort src/warding test
flake8 src/warding test && mypy src/warding
python -m pytest
```

**On macOS, add `--platform linux` to mypy.** CI type-checks on Linux, and
typeshed guards `os.listxattr` / `getxattr` / `setxattr` behind
`sys.platform == "linux"` even though macOS has them — so a local run reports 4
errors in files you did not touch, and it MISSES Linux-only errors CI fails on.
`mypy --platform linux src/warding` is the parity invocation.

**Do not run bare `black src/warding test`.** 1,420 files are not black-clean
yet, so it reformats ~95,800 lines on top of whatever you changed and buries your
diff. The gate above enforces black on every file *outside*
[`.github/black-baseline.txt`](.github/black-baseline.txt) instead, so format only
what you touched: `black --target-version py310 <the files you changed>`. If a
file you touched is listed in the baseline, formatting it is welcome but optional
— do it in its own commit, and prune its line with
`python3 scripts/check_black_formatting.py --update-baseline`.

Frontend: `cd website && npm run build && npm run test`. Faster loops (testmon,
`--lf`, single-file runs) are in
[testing-conventions](docs/system-specs/common/testing-conventions.md). A
multi-test `--override-ini` MUST keep `-n auto --dist loadgroup
--max-worker-restart=2`, because a bare override silently drops `--dist loadgroup`
and scatters `@pytest.mark.xdist_group` tests into flaky races.

Gates you will trip:

| Gate | Rule |
|---|---|
| flake8 F401 | no unused imports |
| flake8 N806 | function-local variables are lowercase (`mock_client`, not `MockClient`) |
| flake8 W504 | line break BEFORE a binary operator |
| mypy | annotate empty collections (`output: list[str] = []`) |
| pytest | `asyncio: mode=strict`, so every async test needs `@pytest.mark.asyncio` |

Never fix a flake with a rerun, a longer `sleep`, or a weakened assertion. Read
[testing-conventions](docs/system-specs/common/testing-conventions.md) § Determinism
for the five flake classes and the one correct fix for each. In particular, a timing
test that asserts algorithmic **complexity** must assert the shape, not a duration —
deterministically where the code has structure to observe (pin the linear path, require
an identical invocation trace when the input doubles), and by a generously-bounded
doubling ratio only where it does not: absolute ceilings split by Python version (CI
enables coverage on 3.12 only), and tight timed ratios false-red on shared runners.

**A test must not touch the operator's machine, and the floor you stand on is not the
same in every testpath.** `testpaths` collects two trees, and only `test/` gets
`test/conftest.py`; the ~108 test modules under `src/warding/apps/builtins/*/tests/`
see the **rootdir** `conftest.py`, plus that app's own `tests/conftest.py` where one
exists (three of the eight apps ship one). So the rootdir conftest carries the
host floor: `WARDING_HOME` pinned per test, the import-time `~/.kiro` bindings pinned
(that directory is kiro-cli's own home, shared with the real installed agent, and a
separate isolation axis from the data home), the SEL default dir pinned session-wide,
`tempfile`'s base redirected with residue reported, and the checkout failed on residue.
Before adding isolation, decide which floor it belongs to; before writing a test, read
the [writing-tests skill](src/warding/builtin_skills/warding-dev/writing-tests/SKILL.md).
Two traps are worth naming here because neither is visible when reading the test:

- **A child process inherits pytest's CWD, the repo root**, so a spawn that may create a
  file needs `cwd=` under `tmp_path` — and the assertion must be scoped to where that
  child actually ran, not to where you hoped it wrote.
- **A singleton with a daemon thread beats every filesystem cleanup.** It captures the
  directory the first caller resolved and re-creates it after a test's own teardown
  deleted it, so the fix is a session-scoped directory owned by no test, never tidier
  cleanup.
- **A stub is not a stop: SPY on a `shutdown`/`close`/`stop` and delegate.** A stub that
  only records leaves the thing running for the whole worker. Replacing the metrics
  provider's `shutdown` left an OpenTelemetry exporter thread alive, and because that SDK
  reinstalls it in every fork child via `os.register_at_fork`, the sandbox probe's child
  became multithreaded — `unshare(CLONE_NEWUSER)` implies `CLONE_THREAD` and fails EINVAL
  there, which was cached as "this host has no sandbox backend" and failed every later
  sandboxed spawn closed. 19 red tests, none of them a metrics test.

## Code style

| Rule | Requirement |
|---|---|
| Line length | 100 chars (black configured) |
| Python version | ≥ 3.10 (`from __future__ import annotations` for type hints) |
| Imports | `import logging` + `logger = logging.getLogger(__name__)` |
| Async | `asyncio` throughout; `async def` for all I/O |
| Dataclasses | `@dataclass` for data containers |
| Constants | No hardcoded strings or values in business logic; every limit has an owning module. Index: [code-style](docs/system-specs/common/code-style.md) |
| Comments | Explain **behavior and rationale (the why)**: invariants, edge cases, units, non-obvious constraints. NOT a task log: no PR/issue numbers, review-round markers, incident dates, milestone tags, or commit SHAs. No "previously/used to/we now" narration, state current behavior in present tense. Don't restate what the code plainly does. `_vendor/` and pragmas are exempt. |
| Icons | **Never use emojis in the UI.** Use `lucide-react` with `className="lucide-inline"`. |
| Product name | The product is **Warding**, and the identifiers carry it too (`warding`, `WARDING_*`, Electron `productName`, slug `myrmitis/warding`). The old identity is retired: CI fails an added line carrying the retired product name glued or joined by one separator (whitespace, `_ - . + / \`, a Unicode dash, `%20`, or a regex spelling of one: an escape, a short character class or a short group), in prose and identifiers alike, env-var prefix included; its data home as a path literal (or a regex of one) or built from split string literals; its hosts and its bundle id, dots plain or regex-escaped; its GitHub org; or its mascot. Only the exact original-work product line in root `NOTICE` is allowed for Apache-2.0 attribution; no file is exempt and there is no inline marker, so a test or gate that names the old identity builds it from fragments. kiro-cli's `~/.kiro` and its own directories, `kiro-cli`, the word "crew", and the two words split by clause punctuation are not flagged. Run `BRAND_BASE_REF=origin/main python3 scripts/check_brand_name.py` before pushing. |
| User-facing strings | The dashboard is translated into 12 languages. **Never hardcode a user-facing English string, and never format a date, number, or sort order without naming a locale.** Both are CI-gated. Backend-owned strings have no catalog path yet, so a new non-2xx JSON body MUST carry a machine-readable `code` field. |

## Cross-platform: route POSIX calls through `platform_compat`

Warding runs on macOS, Linux (x86_64 and ARM), and Windows (native). `fcntl`,
`termios`, `resource`, and `pty` do not exist on Windows, and
**`os.kill(pid, 0)` TERMINATES the target there**: it is not a liveness probe.

| Need | Use (`platform_compat`) | NOT |
|------|--------------------------|-----|
| File lock | `file_lock(fd, exclusive=)` / `acquire_lock`+`release_lock` / `try_acquire_lock` | `fcntl.flock` |
| Liveness probe | `pid_exists(pid)` / `pid_liveness(pid)` | `os.kill(pid, 0)` (kills on Windows!) |
| Kill a process | `kill_pid(pid, sig)` | `os.kill(pid, sig)` |
| Kill a tree | `kill_process_tree(pid, sig)` | `os.killpg(os.getpgid(pid), sig)` |
| Parent PID | `get_ppid(pid)` | `/proc` read / libproc |
| Match process cmdline | `process_matches(pid, needles)` | `/proc/<pid>/cmdline` / `ps` |
| Process start time (PID-reuse guard) | `process_start_time(pid)` | `/proc/<pid>/stat` / `ps -o lstart=` (both answer `None` on Windows, so the guard silently never confirms) |
| Signals | `platform_compat.SIGKILL` / `SIGTERM` | `signal.SIGKILL` (undefined on Windows) |
| Spawn isolation | `start_new_session=IS_POSIX` + `creationflags=CREATE_NEW_PROCESS_GROUP` | bare `start_new_session=True` |
| Re-exec the current Python module | `reexec_python_module(module, args)` | `os.execv(sys.executable, [sys.executable, ...])` (breaks when the Windows interpreter path contains spaces) |
| Race-free Job object assignment | `creationflags \|= CREATE_SUSPENDED`, then `apply_job_limits`, then `resume_process_main_thread` | assigning a job to an already-running child (descendants it already spawned escape) |
| Fork-bomb / memory ceiling on a spawned tree | `sandbox.apply_windows_resource_ceiling(pid)` after the spawn, alongside `cgroup_scope_argv` | `cgroup_scope_argv` alone (a no-op on Windows, so no ceiling at all) |
| File mode | `chmod_safe(path, mode)` / `fchmod_safe(fd, mode)` | `os.chmod` / `os.fchmod` (no `os.fchmod` on Windows) |
| Owner-only secret (fail-loud) | `restrict_to_owner(path)` | `os.chmod(path, 0o600)` under `if IS_POSIX` (silent no-op leaves secrets world-readable) |
| Owner-only secret directory (fail-loud, inheritable) | `restrict_dir_to_owner(path)`; `make_owner_only_dir(path)` to also create it (its tighten step is best-effort) | `restrict_to_owner(path)` on a directory (its Windows grants carry no `(OI)(CI)`, so files created inside land on the default DACL, not owner-only; its `0o600` also drops the execute bit a directory needs) |
| Directory link | `symlink_or_junction(target, link)` | `os.symlink` (`WinError 1314` without elevation) |
| Detect/remove a dir link | `is_link_or_junction(path)` / `unlink_link_or_junction(path)` | `path.is_symlink()` (misses a Windows junction) |
| Process RSS (live) / peak RSS / CPU | `proc_rss_bytes()` / `proc_peak_rss_bytes()` / `proc_cpu_seconds()` | `resource.getrusage` (`ru_maxrss` is a high-water mark, never a live reading, and its unit is KiB on Linux but bytes on macOS) |
| Available host memory | `host_available_mib()` (0 = unknown, never 0 = no memory) | `/proc/meminfo` directly (Linux-only, so the bound built on it silently vanishes on macOS and Windows) |
| FD soft limit | `raise_nofile_soft_limit(n)` | `resource.setrlimit` |
| Port to PID | `find_listening_pids(port)` / `listening_pid_tool_available()`; `find_port_listeners(port)` when ownership must be scoped to the local address actually probed | `lsof` directly |
| Spawn a system tool (`ps`, `lsof`, `netstat`, `taskkill`) | `trusted_system_bin(name)`, treating `None` as "unavailable" | a bare argv name (resolved through a `PATH` that can lead with same-uid-writable dirs) |
| strftime no-pad | `strftime(dt, "%-I")` | bare `dt.strftime("%-I")` (`ValueError` on Windows) |

Verify process, signal, file-lock, and metrics changes on macOS + Linux. Frontend:
Chrome, Firefox, Safari, Edge, using standard Web APIs and guarding the rest.
Windows specifics: [windows-install](docs/guides/windows-install.md).

## LLM-facing capabilities

- **MCP-first.** A new LLM-facing CLI command MUST also ship as an MCP tool
  (`mcp_cron.py` / `mcp_core.py`): kiro-cli calls MCP tools reliably and may refuse
  to run a CLI command via bash. There is exactly one deliberate exception,
  `warding computer call`, a human debug harness rather than a capability; do not
  add another without reading [mcp](docs/architecture/mcp.md). Do NOT add regex to
  match natural-language variants, the LLM interprets NL.
- **MCP tools MUST be stateless.** One server process serves many sessions and
  sub-agents, so no module global may hold per-caller data. Resolve identity per
  call, and use `_resolve_session_key_strict()` for anything that mutates or
  targets a specific session (the lenient resolver walks process ancestors and a
  sub-agent would resolve to its parent slot). Durable state lives behind a gateway
  endpoint keyed by session. Why, plus the `ask_question` reference
  implementation: [mcp](docs/architecture/mcp.md).
- **A skill that any shipped feature, tool, or doc references MUST live in
  `src/warding/builtin_skills/`.** That is the only path bundled into the
  package and copied into the data home's `skills/` directory
  (`~/.warding/skills/` on a new install). Top-level `skills/` is
  repo-checkout-only and reaches no installed user.

## Injected messages are not the user

`[Cron notification from "job"]`, `[Subagent completion event]`, and
`[auto-nudge cycle N]` arrive from automation, not from a human. Process them; do
not answer them as if a user typed them. The user may not be present. Envelope
formats: [injected-messages](docs/system-specs/common/injected-messages.md).

## Harness safety

`warding gateway --approval yolo` auto-approves ALL tools and refuses to start
unless `WARDING_HOME` is explicitly set to a non-default path. Never point it at
`~/.warding`.
All harness flags: [cli](docs/system-specs/modules/cli.md).

## Documentation hub

Read [docs/HUB.md](docs/HUB.md) before material changes. Update the affected canonical documentation in the same PR/commit and link the issue, exact revision, tests and deployment boundary. Automatic `docs/updates/` receipts prove only source pushes. Follow the [shared standard](https://github.com/laqaer/agent-config/blob/main/docs/documentation-hub.md); never copy secrets or customer data into documentation.
