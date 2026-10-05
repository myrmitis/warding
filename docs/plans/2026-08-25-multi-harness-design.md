# Junction — design (2026-08-25)

Junction is a local control plane: dock ACP coding agents and route their
models. The gateway (dashboard, CLI, messaging, cron, memory) stays; the ACP
runtime is pluggable.

## Problem

A typical agent CLI already speaks Agent Client Protocol (JSON-RPC 2.0 over
stdio). The lock-in is spawn + handshake:

- an empty `agent.acp_backend` always means one vendor binary
- protocol version is that vendor's date stamp unless a dormant seam is used
- unknown backends silently degrade to that vendor binary

Junction already runs ACP agents through a registry: Cursor
(`cursor-agent acp`), Claude (`claude-agent-acp`), Codex
(`@agentclientprotocol/codex-acp`), DeepSeek Harness, Kimi (`kimi acp`), Goose,
Grok, Droid, and Pi (`pi-acp`). A single vendor CLI is not a hard requirement.

## Decision

Keep the Python control plane and dashboard. Replace a single-vendor spawn
default with a **runtime registry**.

| Config `agent.acp_backend` | Effect |
|---|---|
| `auto` (default) | First installed of: cursor, claude, codex, kimi, dsh, goose, grok, pi, droid. A vendor CLI only if nothing else is present. |
| `cursor` / `claude` / `codex` / `dsh` / `pi` / `kimi` / `goose` / `grok` / `droid` | That ACP stdio server. ACP protocolVersion `1`. One process per session (`AcpClient`). |
| `kiro` or `""` | kiro-cli path (`AcpRuntime` multiplex). Optional. |
| `kas` | kiro-agent. Optional. |

Unknown values degrade to `auto`, not a vendor CLI.

## Non-goals (this cut)

- Renaming the Python package (`junction`) or moving the data home (`~/.junction`)
- Teaching spec-family agents vendor-only extensions (`_session/steer`, session sharing)
- Wiring a third-party identity fabric into the gateway
