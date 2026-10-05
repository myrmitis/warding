/**
 * The eleven runtimes in the dock registry, in the order `warding planes` lists
 * them (`acp/runtimes.py` AUTO_PREFERENCE: kiro-cli optional and last).
 *
 * A cell is `true` only where a dated row exists on /verified/. Pre-nights the
 * only verified cell is Claude Code · Chat. Everything else renders
 * "registered · unverified"; kiro-cli cells add "first-class harness".
 */
export type Capability = "chat" | "schedules" | "channels" | "approvals" | "overnight";

export const CAPABILITIES: { key: Capability; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "schedules", label: "Schedules" },
  { key: "channels", label: "Channels" },
  { key: "approvals", label: "Approvals" },
  { key: "overnight", label: "Overnight" },
];

export interface Harness {
  id: string;
  /** The CLI binary the registry launches. */
  command: string;
  name: string;
  /** How the harness is reached. */
  via: string;
  /** Verified capabilities: key -> ISO date of the /verified row. */
  verified: Partial<Record<Capability, string>>;
  /** The first-class harness; its cells say "first-class harness". */
  firstClass: boolean;
  optional: boolean;
}

export const harnesses: Harness[] = [
  { id: "cursor", command: "cursor", name: "Cursor", via: "cursor agent (ACP)", verified: {}, firstClass: false, optional: false },
  {
    id: "claude",
    command: "claude",
    name: "Claude Code",
    via: "the ACP project's claude-agent-acp adapter, fetched with npx on first run",
    verified: { chat: "2026-09-25" },
    firstClass: false,
    optional: false,
  },
  { id: "codex", command: "codex", name: "Codex", via: "codex (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "kimi", command: "kimi", name: "Kimi", via: "kimi (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "dsh", command: "dsh", name: "DeepSeek Harness", via: "dsh launcher (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "goose", command: "goose", name: "Goose", via: "goose (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "grok", command: "grok", name: "Grok", via: "grok (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "opencode", command: "opencode", name: "OpenCode", via: "opencode acp (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "pi", command: "pi", name: "Pi", via: "pi (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "droid", command: "droid", name: "Droid", via: "droid (ACP)", verified: {}, firstClass: false, optional: false },
  { id: "kiro-cli", command: "kiro-cli", name: "kiro-cli", via: "kiro-cli (ACP), optional", verified: {}, firstClass: true, optional: true },
];

/** Runtimes people ask about that are not in the registry. Named only in "not yet" sentences. */
export const notDocked = ["Gemini CLI"];

/**
 * The harness router (`src/junction/harness_router/`): chat sessions run the one
 * harness `agent.acp_backend` names; a spawned subagent can be routed to another
 * installed harness. Registered and unit-tested; no routed run is recorded on
 * /verified/, so every surface that shows verification says "registered ·
 * unverified" for it.
 */
export const router = {
  id: "router",
  name: "Harness router",
  command: "warding route",
  what: "sends a spawned subagent to another installed harness: flat-rate plan quota before metered spend, the kind of task, and a cooldown after a usage limit or a failed login. It picks a harness and never forwards provider traffic.",
  verified: false,
} as const;
