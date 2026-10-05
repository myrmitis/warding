# Model router — built-in catalog, no provider forwarding

**This is the change-control contract for `src/junction/model_router/`.**
Read it before changing that package. Update it in the same commit when
behavior documented here changes.

Junction's **model plane** starts with `junction up`. The process binds
`127.0.0.1` (typically `:4202`) and serves `/health` plus `/catalog` from
the shipped snapshot. It does not forward chat completions, does not start
a translation gateway, and does not store provider keys. If that port is
already taken, Junction leaves the existing listener alone and probes it.

Thesis: [`../../../ARCHITECTURE.md`](../../../ARCHITECTURE.md).
Decisions: [ADR 0002](../../adr/0002-two-planes.md),
[ADR 0003](../../adr/0003-sidecar-not-vendor.md),
[ADR 0007](../../adr/0007-builtin-model-catalog.md).
Provenance: [`../../provenance/codex-router.md`](../../provenance/codex-router.md).
Security floor: [ADR 0004](../../adr/0004-security-unchanged.md) — this
module does not weaken keystone, governance, or harness-parity.

## Role

The Python gateway already docks ACP agents (harness plane). The model
plane is a listener in the same process:

| Listener | Typical bind | Role |
|---|---|---|
| Junction catalog | `127.0.0.1:4202` | `/health` and `/catalog`. No provider forwarding. |
| Translation gateway | `127.0.0.1:4200` | Not bundled. Probed only. A busy `:4202` is left alone. |

Ports and host are constants owned by `src/junction/model_router/`.
Call sites import them; they are not restated as literals in CLI chrome
or dashboard copy.

This cut exposes **health**, the **namespaced model catalog**, and a
**role DAG** (orchestration → planning → execution). `junction up` starts
the catalog listener before the compose banner.

`available_models` on ACP clients is a **method**. Role apply calls it;
treating the bound method as a list left every unpinned role on `"auto"`.

`apply_role_model` keeps the existing bare harness-id behavior. A namespaced
id (`provider/model`) is also sent to `set_model` when it is an explicit
`agent.role_models.<role>` pin and the active client advertises it, using the
shared `model_is_unusable` predicate. The namespace is preserved; no model id
is translated to another provider's spelling.

`AcpProvider` wraps the live client and does not re-export `set_model`, so an
admitted namespaced pin reaches the setter through the wrapped client via
`llm_helpers.resolve_substitute_set_model`. Bare ids keep the direct-setter
lookup unchanged; extending wrapper resolution to them is a separate change.

Catalog-only pins, unknown or failed advertisement, and unpinned namespaced
suggestions stay unapplied. Their returned id remains a plan value, not an
execution receipt. A missing setter or setter failure retains the existing
best-effort `auto` return; a failed explicit pin is logged at warning level
with the exception type only, never its message. This compatibility path installs no router, reads
no credentials, and changes no billing configuration. Advertisement proves
only a model-selection option, not authentication, available quota or cost.
An optional external router still needs a separately verified, supported
harness connection; its health alone cannot activate a catalog entry.

Economy roles with no advertised economy id pick the cheapest advertised
id rather than inheriting a flagship session default. Capable and
standard roles still inherit `"auto"` when their class is empty.

## Health and status

Status is a coarse enum the dashboard, CLI, and doctor can show. This
cut does **not** scan the disk for an install (that would look like
credential discovery). A missing listener and a down listener are
the same probe result: `unreachable`.

| Status | Meaning |
|---|---|
| `unreachable` | Neither loopback listener answered. |
| `degraded` | Partial: catalog listener up and `:4200` down, or the reverse. The built-in listener without a translation gateway is this state. |
| `healthy` | Both loopback listeners answer without secrets in the body. |

Health probes hit loopback `/health` and `/health/liveliness`.
They do not scrape env files, capability URLs, or credential stores.

**If the model plane is absent or unhealthy, the ACP gateway still runs.**
That is degraded, documented, and not a crash. Harness sessions do not
depend on `:4202`. Completion routes on the built-in listener return
`501` with `code` `model_router_no_forward`.

## Catalog

`model_router/catalog.json` is a snapshot of Codex Router's namespaced
model choices (slugs, labels, provider ids, listed flag, context window).
It does **not** copy credentials, endpoints, or secret filenames.

- Static providers list every `provider/model` slug the registry ships.
- Live-catalog providers (GitHub Copilot, Groq, local Ollama, …) appear
  as provider rows without hardcoded model ids; the operator curates
  those beside the catalog.
- Grammar for a pin that may be a kiro-cli id **or** a namespaced slug
  is `MODEL_ID_PATTERN` in `catalog.py` (slash allowed as a namespace
  separator; `..`, `//`, `/.`, and a leading or trailing slash are not).

## Role DAG

Roles are `orchestration`, `planning`, `execution`, `background`, and
`subagent` (`ROUTE_ROLE_KEYS`). Edges:

`orchestration → planning → execution → subagent`

`background` is a side node (heartbeat), not on the run path.

Each role has a cost class so tokens buy the most work:

| Role | Cost class | Why |
|---|---|---|
| orchestration | economy | Control traffic; many tokens, little need for flagship capability |
| planning | capable | Rare, high-leverage decomposition |
| execution | standard | Bulk of coding tokens |
| background | economy | Unattended lite workers |
| subagent | standard | Fan-out workers |

Pins in `agent.role_models.<role>` always win. Unpinned roles resolve to
`"auto"` unless the caller supplies an advertised id set, in which case
the pick is an advertised id in that cost class. Concrete model ids are
never hardcoded as defaults. Task-runner decompose uses planning;
execute and self-review use execution / planning via `apply_role_model`.
Orchestrator chat turns (unpinned slots) pick through
`orchestrator_turn_role`: planning for the plan turn, orchestration for
synthetic coordinator turns (subagent synthesis, recovery), and
execution for stage runs. Synthesis is excluded from plan-arming so it
cannot re-count a plan.

`GET /api/model-router/catalog` annotates each slug with `cost_class`.
Settings ▸ Chat lists catalog slugs in the matching class beside
advertised kiro-cli ids, so operators can pin `kimi-oauth/k3` without
typing it.

## Secrets

- Never log provider keys, caller keys, capability URLs, or cookie
  headers.
- Never paste keys into chat, prompts, issues, or health payloads.
- Never copy Codex Router credentials into `JUNCTION_HOME` to “make
  status work.”
- Status JSON carries machine-readable `code` values on non-success;
  it does not echo secret material.

A future `openai_base_url` pointing at a translation listener is operator config
on the **agent** side. Junction does not mint that URL in chat.

## What this module is not

- Not a LiteLLM rewrite.
- Not a vendor of tray, widget, Electron, public Cursor HTTPS tunnel, or
  Codex Router's experimental ACP agent bridges (those overlap
  `src/junction/acp/runtimes.py` — do not copy).
- Not a governance scope (`computer_use.*` stays off limits; the model
  plane is not computer use).
- Not a second `agent.provider`. Harness selection stays
  `agent.acp_backend`.

## Invariants

1. Serve the catalog on loopback. Do not vendor another product's tree.
2. Loopback only.
3. Degrade open: missing translation gateway ≠ gateway failure.
4. No secrets in logs, status, or chat.
5. Positive harness identity elsewhere is untouched by this package.

## This-cut surface

- CLI: `junction up` (compose then serve; `junction gateway` is the same
  server), `junction planes` (human; `--json` for the machine snapshot of
  harness inventory, model-plane health, and the role DAG), `junction doctor --quick`
  (compose-only), `junction doctor` (Planes section first, then the full probe),
  `junction router status`, `junction router catalog`,
  `junction router plan`. Human text for planes, doctor, and the `up` banner
  is one formatter. `junction router` human lines name the model plane and
  never claim a sidecar injects provider keys.
- HTTP: `GET /api/planes` (harness inventory + model-plane health + role DAG),
  `GET /api/model-router/status`, `GET /api/model-router/catalog`,
  `GET /api/model-router/plan`. An unreachable plane is degraded, not a 5xx.
  The built-in listener adds `GET /health` and `GET /catalog` on its own port.
- Probe URLs: `http://127.0.0.1:{router}/health` and
  `http://127.0.0.1:{gateway}/health/liveliness`. Ports come from
  `model_router.probe` (`DEFAULT_ROUTER_PORT` 4202, `DEFAULT_GATEWAY_PORT`
  4200) and the `MODEL_ROUTER_PORT` / `CODEX_ROUTER_PORT` environment
  variables Codex Router already honors.
- Config: `agent.role_models` and `agent.role_efforts` keys listed in
  `ROLE_MODEL_KEYS`. Each role is declared in the config schema as
  `agent.role_models.<role>` / `agent.role_efforts.<role>`, so its
  Settings ▸ Chat control carries that path as a `configKey`.
