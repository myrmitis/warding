# Harness router — send each task to the subscription that should do it

**This is the change-control contract for `src/junction/harness_router/`.**
Read it before changing that package, the `harness` / `kind` fields on
`spawn_run`, or the per-session `acp_backend_override` factory seam. Update it
in the same commit when behavior documented here changes.

Warding docks coding-agent harnesses from one registry — Claude Code, Codex
(ChatGPT), Cursor, Grok Build, OpenCode (OpenRouter and every other provider it
logs into), and the rest of `acp/runtimes.py`. Each is reached through a plan
or account the operator already pays for. Chat sessions run the one harness
`agent.acp_backend` names; the harness router decides which installed harness
takes each unit of work handed to a spawned subagent. It **chooses a harness**; it never
forwards provider traffic, stores a key, or reads a harness's credentials. The
chosen harness runs with its own login, exactly as `agent.acp_backend` would.

Related: [harness-parity](harness-parity.md) (what an added harness may and may
not change), [model-router](model-router.md) (the model plane, which this does
not touch), [subagent](subagent.md) (where routed work runs), [mcp](../../architecture/mcp.md).

## Vocabulary

| Term | Meaning |
|---|---|
| **Harness** | An ACP backend id from `acp/types.py`, spelled for operators (`kiro` for the empty backend). |
| **Lane** | One subscription or account reached through one harness: `id`, `harness`, `billing`, `weight`, `window_hours`, `window_limit`, `daily_limit`, optional `model`, per-kind `affinity`. Two lanes may share a harness (an OpenCode lane on a cheap OpenRouter model for bulk work, another on a strong one for review). |
| **Kind** | What the work is: `plan`, `implement`, `debug`, `review`, `test`, `research`, `docs`, `quick`, `bulk` (`kinds.TASK_KINDS`). The calling agent names it as an enum; the router never guesses it from free text. |
| **Billing** | `subscription` (flat plan with a usage window), `free`, or `metered` (pay per token). |
| **Ledger** | `<data home>/routing/ledger.json`: per-lane dispatch timestamps, outcome counters, cooldown deadline, the harness that produced or cleared the cooldown reason, and a truncated, credential-redacted last error. Never prompts or keys. |

## Objective

Maximum useful work from what the operator already pays for:

1. **Spend flat-rate quota first.** Unused subscription quota is lost at reset,
   so metered lanes compete at `METERED_FACTOR` (0.6) of their score.
2. **Spread load by headroom.** A lane's dispatches in its rolling window are
   compared with its capacity (`window_limit` when stated, else `weight ×
   NOMINAL_WINDOW_DISPATCHES`). A lane near its cap yields to one with room.
3. **Match the task.** Affinity for the kind decides between lanes with similar
   headroom.
4. **Rest a lane in trouble.** A lane resting after a lane-level failure is
   excluded until its cooldown ends; a lane past `daily_limit` is excluded; a
   lane at `window_limit` falls behind every lane with room (`EXHAUSTED_FACTOR`)
   but is not excluded, since a stated limit may be conservative.

`score = billing_factor × (0.6 × affinity + 0.4 × headroom)` (+ a small bonus
for a caller's `prefer`). Scoring (`router.decide`) is pure over settings,
ledger snapshot and the installed set, so it is deterministic and testable
without spawning anything. Ties break by lane order in `routing.json`.

Default affinities live in `profiles.HARNESS_PROFILES`: Claude Code leads plan,
review and docs; Codex leads implement, debug and test; Grok leads research;
Cursor leads quick edits; OpenCode is metered and favours bulk. They are a
starting point for a zero-config install, not a benchmark — `routing.json`
overrides any of them per lane.

## Lanes and `routing.json`

`<data home>/routing.json` holds `enabled`, `max_failover` (default 2),
`route_tasks` (default `false`; see § Task-runner steps) and a `lanes` list. It carries no credentials. With no file, every installed harness
becomes one lane with its built-in profile (`source: "auto"`), and that set
tracks installs without a restart. A present-but-unparseable file degrades to
the detected lanes with a warning: routing is never the reason a gateway cannot
start. Invalid lanes are skipped with a warning, never guessed at. `warding
route init` writes a template from the installed harnesses.

```json
{
  "enabled": true,
  "max_failover": 2,
  "lanes": [
    {"id": "claude-max", "harness": "claude", "billing": "subscription", "weight": 3},
    {"id": "chatgpt-pro", "harness": "codex", "billing": "subscription", "weight": 3},
    {"id": "cursor-pro", "harness": "cursor", "billing": "subscription"},
    {"id": "supergrok", "harness": "grok", "billing": "subscription"},
    {"id": "openrouter", "harness": "opencode", "billing": "metered",
     "model": "openrouter/deepseek/deepseek-v4", "daily_limit": 200}
  ]
}
```

A lane's `model` is spelled for **its own harness** and is sent only to that
harness (H12). A routed subagent never inherits `agent.role_models.subagent`,
which is spelled for the configured default harness.

## Failure classes and cooldowns (`limits.py`)

| Class | Examples | Rest when no reset is stated |
|---|---|---|
| `usage_limit` | "usage limit reached", "5-hour limit", "Insufficient credits" | 60 min |
| `rate_limit` | 429, "rate limit", "overloaded", `AcpTurnStalled` (a harness silent while retrying its provider) | 2 min |
| `auth` | `AcpAuthRequired`, "Authentication required", "run /login" | 30 min |
| `unavailable` | harness binary missing, "is not installed" | 10 min |
| `other` | an ordinary task failure | none — it would fail on any lane |

A stated reset ("try again in 2 hours 5 minutes", "resets 3pm", Claude's
`|<epoch>` suffix) wins over the default, clamped to `[30 s, 8 days]`. Clock
times are read in the host's local zone. A success clears a lane's cooldown.

Some harnesses end a turn normally with the limit notice as the whole reply.
`limit_notice_failure` treats a reply as a lane failure only when it is short
(`LIMIT_NOTICE_MAX_CHARS`), starts with a recognizable usage-limit or auth
notice, and the turn ran no tools. Short answers such as `Run codex login`
or explanations of a daily limit remain successful output. The broader
exception classifier is not applied to successful replies; `rate_limit` is
never inferred from them.

## Dispatch

### Subagents (`spawn_run`)

`spawn_run` takes `harness` (batch-wide) or `harnesses[]` (one per task), and
`kind` / `kinds[]`. `harness` is `route` (the router picks), a lane id, or a
harness name. The gateway's `POST /api/spawn` resolves it **before** the
submission is counted, so a refusal is an ordinary 400 with a `code`. The
response carries `route` (lane, harness, model, kind, routed, reason).

`SubagentInfo` gains `harness`, `lane`, `route_kind`, `routed`. In `_run_inner`
a set `harness` becomes the factory kwarg `acp_backend_override` and forces the
dedicated-process path (the parent's shared runtime is a different harness).
`state.json` persists `harness` and `lane`, and `continue_conversation`
continues on them: a conversation lives in the harness that ran it.

`SubagentManager._run_accounted` wraps `_run_inner` for a run with a lane:

- records a dispatch, then the outcome, in the ledger;
- on a lane-level failure of a **routed** run with no tool activity, not a
  continuation, not user-stopped, and within `max_failover` hops, tears the
  session down and re-runs on `router.next_lane(kind, tried)`, firing
  `subagent_retrying` with `{lane, harness, failed_lane}` and a
  `subagent.harness_failover` SEL record;
- an explicit pin (`routed=False`) never moves; its failure still rests the lane.

A run with no lane passes straight through: the unrouted path is unchanged.

### Task-runner steps

Opt-in with `route_tasks: true`; off, every step runs on the configured agent
exactly as before (invariant 2). The run fixes the choice when it first
executes (`Project.route_steps`, persisted). `task_routing.StepRoute` applies the
subagent rules to a step, with two differences that follow from a step being
retried by the task runner rather than re-run from scratch:

- the planner names the step's kind (`Task.kind`; unnamed routes as
  `implement`), and the self-review is its own dispatch of kind `review` that
  prefers a lane on a different harness than the one that did the work;
- a lane-level failure always releases the lane, so the next attempt goes to
  the next best one. It is a free move (not counted as an attempt) only before
  any tool ran and within `max_failover` moves per step; after tool use (including approved child permissions and child tool notifications) it
  costs an attempt instead of being refused, because the task runner retries
  the step with the previous error in the prompt either way.

As for routed subagents, a turn that ends normally with only the harness's
limit or login notice as its reply (`limit_notice_failure`) and ran no tool is a
lane failure (`HarnessLaneFailure`), not a result. Notice text is credential and
exfiltration-URL redacted before it enters exceptions or logs. A routed review that fails at
lane level moves to the next lane for free in the same way; any other review
failure stays non-blocking. The review collector observes native child tools
by their tool-call ids too, so a review that performed child tool work is not
replayed on another harness; text-only child activity does not count.

A step also keeps its lane across a pause or gateway restart: the executor
saves the lane and its model on the task (`Task.lane_id`, `Task.lane_model`)
before every dispatch, and `StepRoute.for_task` restores them instead of
re-scoring headroom that the step's own dispatch already reduced. The router
never swaps the saved lane for another provider. (Task-step sessions are
stateless, so a resumed step is a fresh conversation on that lane, not a native
session reload.) If it is gone, disabled,
re-pointed at another harness, not installed, resting, or at its daily cap, the
resume fails closed with `RoutingError` (`lane_unavailable` / `daily_cap`) and
records no dispatch. A step that fell back to the configured agent resumes there.
A restored lane's first lane-level failure costs an attempt, since it may have
worked already. Contract and persistence: [taskrunner](taskrunner.md) § Step
Routing.

A step keeps its lane across ordinary retries, runs on a dedicated provider for
the lane's harness and model (`open_task_session(acp_backend_override=,
model=)`), and never receives a role-model pin (H12). Each sticky retry checks
the lane's current hard daily dispatch cap before reserving usage; reaching the
cap refuses the retry without moving its conversation to another lane.
Selection refusal is terminal without a fabricated dispatch outcome, another
attempt, or a live-session reset. Execution success is recorded only after its
automatic verification tests pass; red tests record an ordinary failed attempt
on the same lane, never a harness outage inferred from test-output prose. Cross-lane process moves are governed by
`max_failover` and the task attempt budget, not ordinary process recovery.
Initially no eligible lane runs the step on the configured agent unless a
hard daily cap excluded a candidate; budget refusal never falls back unaccounted. After a lane failure, exhausting the
eligible lanes fails the step rather than retrying a cooling harness without
lane accounting. Dispatches and outcomes go to the same ledger as
other routed work. Parallel step selection and dispatch recording share a
process-local transaction, so each gateway step reserves its usage before the
next step scores the ledger; model execution remains parallel. The ledger is
shared with subagents, so a limit hit by a step rests that lane for every later decision.
This transaction serializes task steps in this process only; existing subagent
resolve/dispatch calls and other processes do not share its reservation lock.
Contract for the runner side: [taskrunner](taskrunner.md) § Step Routing.

### The provider-factory seam

`JunctionConfig.create_provider_factory()`'s closure takes an optional
`acp_backend_override`. Absent, the configured `agent.acp_backend` is used
exactly as before. Present, `resolve_acp_backend_override` maps `kiro` to `""`
and **raises** on an unknown value — an override is an explicit per-call choice,
and running a different harness than the one named is what H3/H8 forbid. The
warm pool is bypassed with decision `bypass_harness`: pooled processes run the
configured backend and a claim only re-keys and re-models them.

The model the factory hands the provider is scoped to the harness that will run
it, never to the configured default (H12). A caller's `model_override` — the
lane's own model, spelled for its harness — wins outright, passed through
untouched except on the kiro namespace, where a canonical registry key is
translated with `model_registry.to_acp_id`. With no explicit pick, a **named**
Kiro pin (the named kiro agent's model slot) is allowed whenever the target
harness is in the kiro namespace (`ACP_BACKENDS_KIRO_MODELS`, kiro + kas), while
the configured global `agent.model` applies only when the target harness is the
configured one — so an override onto kiro from a Codex-configured install does
not inherit the Codex model, and a foreign **configured** harness keeps the
`agent.model` the operator pinned, spelled for that harness, while the value
derived from the kiro agent spec is never sent to it. No model id crosses a
distinct harness identity in either direction. `auto` is resolved once, at
provider creation, with `acp.runtimes.select_runtime`: the provider receives the
**concrete** backend, so the model namespace and the running harness come from a
single decision. `auto` is retained, and no model inherited, only when no
runtime resolves.

**Caution.** Because the provider now receives the concrete backend, an existing
session persisted under `auto` may see a single provider-switch replay after
upgrade. Live behavior is unverified.

### Terminal (`warding route run`)

Runs one prompt on the resolved lane with the same failover rules, streaming to
stdout. Tool permission requests are asked at the terminal when both ends are a
TTY, else denied (`--no-prompt` forces deny). It warms the sandbox probe before
the event loop starts, because the probe never runs on a live loop.

## Connecting harnesses (`connect.py`)

Warding never performs a sign-in and never sees a credential. "Connecting" an
agent means running that agent's own login command, then probing it.

- `HARNESS_SETUP` holds the install and login shell commands and a docs URL for
  the featured subscriptions (Claude Code, Codex, Cursor, Grok Build, OpenCode).
  Claude's install names `@agentclientprotocol/claude-agent-acp` too: Warding
  drives Claude Code through that adapter, which the `claude` CLI does not ship.
  Other registry harnesses show their runtime `login_hint` instead.
- `probe_harness` starts the harness exactly as a session would (provider
  factory, sandboxed, `acp_backend_override`) and runs `initialize` +
  `session/new`. **No prompt is sent, so a probe spends no plan quota.** The
  outcome is one of `connected`, `needs_login`, `not_installed` (including a
  missing adapter), `timeout`, `error`, and is persisted with a redacted,
  truncated detail and the models the harness advertised (`advertised`, its own
  ids, at most `PROBE_MODELS_MAX`) in `<data home>/routing/harnesses.json`.
  `warding route check` and the dashboard share it. The complete read/merge/
  atomic-replace transaction holds `platform_compat.file_lock` on the stable
  sibling `harnesses.lock`, shared by all harnesses and store instances.
  Concurrent completions retain each harness and its advertised model ids.
- **A probe does not verify sign-in.** A harness can open a session on an
  expired login and fail only at the first prompt: claude-agent-acp has probed
  `connected` while a routed prompt on it failed with "OAuth session expired".
  So `warding route check` prints a `connected` probe as `auth unverified`,
  names `warding route run --harness LANE` as the verifier, and exits 0. It
  prints `needs_login` with the login command, and exits 1, when the lane's
  ledger `cooldown_reason` is still `auth` and the ledger's `harness` is the
  lane's current harness: a success or `route clear` empties that reason, so it
  means no prompt on that harness has worked since a failed sign-in, even after
  the rest expired. A lane id reassigned to another harness, or a record that
  names no harness, stays `auth unverified`. The ledger is read after that
  lane's probe returns, so a routed run that ends during a minutes-long probe
  counts. An ordinary task failure retains
  both the cooldown reason and its producing harness; it cannot attribute an
  older sign-in failure to the harness that ran that task. A success from a
  harness the lane no longer runs (a run that outlived a reassignment) counts as
  a completed run but leaves the failure state alone, because it says nothing
  about the harness the lane runs now; a success on the current harness clears
  it, whichever harness recorded it. The ledger resolves the lane's current
  harness itself, while it holds its lock, so a reassignment and a failure
  recorded for the new harness cannot land between the lookup and the write.
  The stored probe
  status stays `connected`; the gates below read it as "the harness starts".
- `service.check_harness` (probe now) and `service.verified_connection` (reuse a
  `connected` probe younger than `max_age_secs`, else probe) hold one lock per
  harness, so a double-clicked Check or a burst of gated requests starts one
  process. The dashboard's readiness gate uses the latter; see below.
- Settings ▸ **Agents & plans** (`website/src/pages/settings/AgentsPanel.tsx`)
  renders one card per agent: status, Install / Sign in (typed into the
  dashboard's dock terminal, or copied when the terminal is off), Check, and the
  lane controls (use for routing, billing, plan size, window limit, model),
  plus the current pick per kind. On first load it probes every installed agent
  that was never checked. Every displayed word is a catalog key; commands and
  statuses are machine data.
  The task-step routing switch writes `routing.json`, not the main config
  hierarchy. Its `routing.route_tasks` UI key supports direct Settings links
  and highlighting; the drift guard validates this separate namespace against
  routing.json's editable fields and parser, not the main config schema.
- The first-run gate shows the same panel in compact form above the Kiro steps,
  with **Continue with these agents** once any agent is connected
  (`POST /api/kiro-prerequisite/complete-with-agents`). kiro-cli is optional.

## The dashboard on a non-Kiro agent

The session manager resolves the harness new dashboard turns run on
(`SessionManager.resolved_backend()`: `agent.acp_backend` with `auto` resolved
through `acp.runtimes.resolve_backend`, cached for 60 s). Everything that used to
assume kiro-cli reads it:

| Surface | kiro-cli / KAS | Any other agent |
|---|---|---|
| Regenerate, edit-resend, rewind, `/v1/chat/completions` | Kiro prerequisite gate | `verified_connection` (5 min, 45 s budget); 503 `harness_not_connected` unless `connected` |
| `/api/models` | `kiro-cli --list-models` | that agent's advertised models: newest live session, else last probe; `auto` first; 503 `harness_models_pending` while neither exists |
| `/api/sessions/usage` | Kiro credit scrape | `{"available": false, "reason": "harness_not_kiro"}` (pill hidden) |
| Task runner steps | shared `AcpRuntime` | one dedicated provider per step on the configured agent |
| Background one-liners | `_bg` runtime session | provider-backed `_ProviderBgSession` |

Membership is `ACP_BACKENDS_KIRO_READINESS` (gates) and
`ACP_BACKENDS_ACP_RUNTIME` (runtime hosting), both positive sets (H5/H6). An
unreadable active backend answers kiro-cli, which keeps the fail-closed Kiro
gate.

## Surfaces

| Surface | What |
|---|---|
| `warding route` / `route status [--json]` | Lanes, windows, 24h use, cooldowns and last error, current pick per kind |
| `warding route pick KIND` | Rank every lane for a kind (twin of `route_task`) |
| `warding route run [-k KIND] [--harness T] PROMPT` | One prompt on the routed lane, with failover |
| `warding route check [LANE…]` | Start each harness once (initialize + session/new, no prompt): installed? starts? A start reads `auth unverified`; a lane whose last routed run failed sign-in reads `needs_login` |
| `warding route init [--force] [--all]` | Write `routing.json` from the installed harnesses |
| `warding route clear [LANE]` | Lift a cooldown early |
| MCP `route_task(kind, prefer?)` | Read-only ranking for the agent splitting the work |
| MCP `spawn_run(harness, harnesses[], kind, kinds[])` | Routed or pinned dispatch |
| `GET /api/routing/status` | Same payload as `route status --json` |
| `GET /api/routing/decide?kind=&role=&prefer=&exclude=` | One decision; "no lane" is a 200 with `code: no_lane` |
| `POST /api/routing/cooldown/clear {lane?}` | Lift a cooldown |
| `GET /api/routing/harnesses` | Every connectable agent: installed, last probe, setup commands, its lane, picks per kind |
| `POST /api/routing/harnesses/{harness}/check` | Probe one agent now (one at a time per agent) and record the result |
| `PUT /api/routing/settings` | Change routing.json switches (`route_tasks`); `400` `invalid_settings_edit` on an unknown field or non-boolean value. Same materialize/refuse rules as the lane edit |
| `PUT /api/routing/harnesses/{harness}/lane` | Edit that agent's lane (`enabled`, `billing`, `weight`, `window_limit`, `daily_limit`, `model`) in `routing.json`; `400` `invalid_lane_edit` on a bad value. A missing file is materialized from the detected lanes; a broken one is refused, never overwritten |

`/api/routing` is a mixed internal path (MCP secret or dashboard cookie).
Handlers do their file I/O off the event loop.

## Invariants

1. **Choose, never forward.** No provider traffic, keys, or credential reads.
   OpenRouter reaches Warding as the OpenCode harness logged into it.
2. **Unrouted is unchanged.** No lane ⇒ `_run_inner` directly; no override ⇒
   the configured backend; the Kiro path gains no conditional (H13). Task-runner
   steps route only when `route_tasks` is on.
3. **Explicit beats routed.** A named lane or harness never silently moves.
4. **Only lane failures move work, only before activity.** An ordinary task
   failure never rests a lane; a run that executed a tool never re-runs.
5. **Accounting never fails a run.** Ledger and settings errors are logged and
   swallowed; a corrupt ledger starts fresh.
6. **No secrets at rest.** The ledger stores redacted, truncated error text.

Pinned by `test/test_harness_router.py`, `test/test_harness_router_notices.py`,
`test/test_harness_probe_store.py`, `test/test_harness_readiness_gate.py`,
`test/test_task_routing.py`, and the per-harness cases in `test/test_session.py`.
Those are unit and integration tests with the harness faked; no routed run on a
live harness, and no OpenCode session, is recorded as verified yet.
