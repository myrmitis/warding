import type { AgentSource } from "./types";

/**
 * The scripted night (site-spec §2). Step 0 is the hero; steps 1–5 are the
 * clock-time sections, driven by the page's IntersectionObserver through the
 * `warding:step` event. Everything here is simulated and labelled as such in
 * the frame; the renderer is the shipping one.
 */
export interface Beat {
  step: number;
  time: string;
  sources: AgentSource[];
  /** Agents that walk in from the door on this beat even if already present. */
  reenter?: string[];
  /** The agent acting on this beat; the hero frame pans to its desk. */
  focus: string;
}

const CLAUDE = { id: "claude", label: "claude", kind: "slot" as const, detail: "fix/auth-flake" };
const CRON = { id: "cron-nightly", name: "Nightly Build", label: "cron", kind: "cron" as const, detail: "0 2 * * *" };
const SPAWN = { id: "spawn-tests", name: "tests", label: "subagent", kind: "spawn" as const, detail: "subagent" };

export const BEATS: Beat[] = [
  {
    step: 0, time: "02:14", focus: "claude",
    sources: [
      { ...CLAUDE, name: "claude", running: true, pendingApproval: { tool: "git push", requestId: "sim-1" } },
      { ...CRON, running: true },
      { ...SPAWN, running: true },
    ],
  },
  {
    step: 1, time: "22:40", focus: "claude",
    sources: [{ ...CLAUDE, name: "claude", running: true, lastMessage: "fix the flaky auth test and open a PR" }],
    reenter: ["claude"],
  },
  {
    step: 2, time: "01:12", focus: "cron-nightly",
    sources: [
      { ...CLAUDE, name: "claude", running: true },
      { ...CRON, running: true, lastMessage: "Nightly Build Watch · fired" },
    ],
  },
  {
    step: 3, time: "02:30", focus: "claude",
    sources: [
      { ...CLAUDE, name: "claude", running: true, refused: "~/.aws" },
      { ...CRON, running: true },
    ],
  },
  {
    step: 4, time: "03:05", focus: "claude",
    sources: [
      { ...CLAUDE, name: "claude", running: true, pendingApproval: { tool: "git push", requestId: "sim-2" } },
      { ...CRON, running: true },
      { ...SPAWN, running: true },
    ],
  },
  {
    step: 5, time: "07:00", focus: "claude",
    sources: [
      { ...CLAUDE, name: "claude", running: false, lastMessage: "PR #412 opened" },
      { ...CRON, running: false, lastMessage: "nightly-deps · done" },
    ],
  },
];

/** Step 4 after the visitor taps Approve or Deny (nothing auto-approves). */
export function resolvedBeat(action: "approve" | "deny"): Beat {
  return {
    step: 4, time: "03:05", focus: "claude",
    sources: [
      { ...CLAUDE, name: "claude", running: action === "approve", lastMessage: action === "approve" ? "approved · pushing" : "denied · returning" },
      { ...CRON, running: true },
      { ...SPAWN, running: true },
    ],
  };
}

export const REDUCED_MOTION_STEP = 3;
