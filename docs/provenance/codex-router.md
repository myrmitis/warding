# Provenance — Codex Router

Junction's model plane **observes** [Codex Router](https://github.com/duolahypercho/codex-router)
(`duolahypercho/codex-router`, MIT, on the order of 3.7k GitHub stars).
Junction is not Codex Router, does not vendor it this cut, and does not
claim affiliation.

Codex Router's own README states it is an independent community project,
not affiliated with or endorsed by OpenAI, GitHub, Anthropic, Moonshot
AI, DeepSeek, OpenRouter, opencode, Google, or the referenced opencodex
project. Junction repeats that disclaimer; it does not add a new one in
their name.

## What it actually does

A local loopback router, not a hosted proxy:

- **`:4202`** — Codex Responses listener (and the OpenAI-compatible path
  agents use as `openai_base_url`).
- **`:4200`** — LiteLLM, which translates that contract to each
  provider's native protocol (Chat Completions, Anthropic Messages, …)
  with streaming and tool-call shapes preserved.
- **Namespaced catalog** — routed models appear as router-owned slugs,
  not as fake subscription models in another client's picker.
- **Credential isolation** — the caller authenticates to the router; the
  router passes a random internal key to LiteLLM; the forwarder injects
  only the selected provider credential. Secrets stay on the machine.
  Health routes do not expose them. Credentials are entered through
  hidden local prompts, never pasted into chat.

Every listener binds to `127.0.0.1`.

## What overlaps this repository — do not copy

Codex Router also ships:

- tray / menu-bar app, desktop widget, Electron Control Center
- a public Cursor HTTPS tunnel
- experimental ACP **agent bridges** (Claude Code, Cursor Agent, Gemini
  CLI session bridges)

Those agent bridges overlap this checkout's ACP runtime registry. They
are a second way to drive the same clients. Junction does not copy them.
Harness docking stays in `src/junction/acp/runtimes.py`.

Do not copy tray, widget, Electron, or the HTTPS tunnel. Do not
reimplement LiteLLM. ADR: [0003](../adr/0003-sidecar-not-vendor.md).

## This cut

`junction up` serves loopback health and the shipped catalog from
`src/junction/model_router/`. Catalog JSON copies slugs and labels only
(MIT registry metadata, no credentials, no endpoints). Provider
translation is not bundled. Junction does not vendor the Node tree.
