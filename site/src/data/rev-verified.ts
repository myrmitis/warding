import { CAPABILITIES, harnesses, type Capability } from "./harnesses";

/**
 * The verification log (/verified/). One row per harness × feature; a row is
 * `verified` only when a dated run is recorded, and every checkmark elsewhere
 * on the site links to its row here by id (`<harness>-<feature>`, the same
 * anchor the homepage matrix and /registry/ use).
 *
 * Rows are added from one dated log in the repository,
 * `docs/business/verified.md`, once a run is recorded there; nothing here is
 * written from memory. Today exactly one row is verified.
 */
export type VerifiedStatus = "verified" | "unverified";

export interface VerifiedRow {
  /** Anchor id: `<harness id>-<feature key>`. */
  id: string;
  harness: string;
  harnessName: string;
  /** How the harness is reached (from the registry). */
  via: string;
  feature: Capability;
  featureLabel: string;
  /** "" when no run is recorded. */
  machine: string;
  /** ISO date of the recorded run, or "". */
  date: string;
  evidence: string;
  status: VerifiedStatus;
  /** Extra context, e.g. why a row is not run here. */
  note: string;
}

type Recorded = Pick<VerifiedRow, "machine" | "date" | "evidence" | "status" | "note">;

/** The runs that have actually been recorded, keyed by row id. */
const recorded: Record<string, Recorded> = {
  "claude-chat": {
    machine: "Linux x86_64 container",
    date: "2026-09-25",
    evidence:
      "one-shot chat returned a reply via the ACP project's claude-agent-acp adapter (the same adapter the registry now fetches with npx on first run)",
    status: "verified",
    note:
      "The adapter was installed by hand for this run; the npx fetch on first run landed the day after and has not been re-recorded. The container has no user namespaces, so the OS sandbox was opted out with its loud warning.",
  },
};

const KIRO_NOTE = "first-class harness · not run here";

export const verifiedRows: VerifiedRow[] = harnesses.flatMap((h) =>
  CAPABILITIES.map((c) => {
    const id = `${h.id}-${c.key}`;
    const run = recorded[id];
    return {
      id,
      harness: h.id,
      harnessName: h.name,
      via: h.via,
      feature: c.key,
      featureLabel: c.label,
      machine: run?.machine ?? "",
      date: run?.date ?? "",
      evidence: run?.evidence ?? "no run recorded",
      status: run?.status ?? "unverified",
      note: run?.note ?? (h.firstClass ? KIRO_NOTE : ""),
    };
  }),
);

export const verifiedCount = verifiedRows.filter((r) => r.status === "verified").length;
export const notRunHereCount = verifiedRows.filter((r) => r.note === KIRO_NOTE).length;
export const unverifiedCount = verifiedRows.length - verifiedCount - notRunHereCount;

/** Verified rows first, then the registry order. */
export const verifiedRowsSorted: VerifiedRow[] = [
  ...verifiedRows.filter((r) => r.status === "verified"),
  ...verifiedRows.filter((r) => r.status !== "verified"),
];

/** Work that is not verified yet, stated so nobody has to infer it from the gaps. */
export interface NotYet {
  what: string;
  status: "planned" | "being verified";
  detail: string;
}

export const notYet: NotYet[] = [
  {
    what: "Overnight runs on any harness",
    status: "planned",
    detail:
      "The service mode, cron and the task runner ship; no night has been recorded on any harness. Three dated Claude Code nights are the gate for the site's stronger copy.",
  },
  {
    what: "Channels, schedules and approvals on a non-Kiro harness",
    status: "planned",
    detail:
      "The gateway and channel code is shared across harnesses, though each harness has its own capability flags (session sharing, steering, its own sandbox), and nobody has run a channel round-trip, a scheduled job or an in-chat approval on Claude Code, Codex or the others at runtime.",
  },
  {
    what: "The harness router: a subagent sent to another harness",
    status: "planned",
    detail:
      "Registered · unverified. Chat sessions run the one harness you choose; the router can send a spawned subagent to another installed harness (flat-rate quota before metered, task kind, a cooldown after a usage limit or a failed login), and it never forwards provider traffic. It is covered by unit tests; no routed run on a live harness has been recorded, and neither has an OpenCode session.",
  },
  {
    what: "The Telegram round-trip on Claude Code",
    status: "planned",
    detail: "The homepage shows it as a simulation and says so in the caption.",
  },
  {
    what: "“The default build contacts no server of ours”, checked with lsof",
    status: "planned",
    detail:
      "The update feed, app catalog and telemetry are off in the default build; the run that lists every outbound connection during a session has not been done. The embedding model is still fetched on first embedding use from a third-party CDN address.",
  },
];

/** Where a new row comes from. */
export const rowSource = {
  path: "docs/business/verified.md",
  exists: false,
};
