import type { Rail } from "./pricing";

/**
 * The parts of /pricing/ that are not an offer: the comparison table, the
 * FAQ (site-spec §3, audited wording), the three Hosted waitlist questions
 * and the rail labels. Offers themselves come from ./pricing.ts.
 */
export const RAIL_LABEL: Record<Rail, string> = {
  none: "No payment. Apache-2.0.",
  polar: "Paid through Polar, which handles tax and receipts",
  stripe: "Paid through a Stripe checkout",
  github: "Through GitHub Sponsors",
  waitlist: "Free list; nothing is charged",
};

/** Cell states for the comparison table. */
export type Cell = "included" | "day-one" | "not-built" | "none";

export interface ComparisonRow {
  label: string;
  cells: Record<string, Cell>;
}

/** Offer ids in column order; hidden offers are dropped by the page. */
export const comparisonColumns = ["free", "supporter", "setup", "pilot", "team", "hosted"];

const row = (label: string, cells: Record<string, Cell>): ComparisonRow => ({ label, cells });
const all: Cell = "included";

export const comparison: ComparisonRow[] = [
  row("Everything in the tree", { free: all, supporter: all, setup: all, pilot: all, team: all, hosted: all }),
  row("Numbered seal badge", { supporter: "day-one" }),
  row("The Vault scene (Agent Worlds)", { supporter: "day-one" }),
  row("Charter Paper and Warding Night theme pack", { supporter: "day-one" }),
  row("Roadmap vote", { supporter: "day-one" }),
  row("Sixty-minute setup session", { setup: "included", pilot: "included" }),
  row("Central policy authoring and signed push", { pilot: "not-built", team: "not-built" }),
  row("Audit forwarding to your SIEM", { pilot: "not-built", team: "not-built" }),
  row("Dashboard SSO", { team: "not-built" }),
  row("A box we run", { hosted: "not-built" }),
];

export const CELL_LABEL: Record<Cell, string> = {
  included: "Included",
  "day-one": "Day one",
  "not-built": "Not built yet",
  none: "Not included",
};

export const hostedQuestions = [
  { id: "would-pay", label: "What would you pay per month for a box we run, with your own agent subscription?" },
  { id: "harness", label: "Which harness would you dock? (Claude Code, Codex, Goose, kiro-cli, another)" },
  { id: "channel", label: "Which chat channel would you reach it from?" },
];

/** Answers are authored here, not user input; they may carry site-relative links. */
export const faq: { q: string; a: string }[] = [
  {
    q: "Do I need to pay you to use my own Claude plan, Codex or kiro-cli?",
    a: "No. Warding launches the official CLI under your own login. We never see your keys and we never mark up tokens.",
  },
  {
    q: "Is there a run cap?",
    a: "Not from us. Your vendor's plan limits and their terms for unattended use apply and may change; for shared or production automation, use an API key.",
  },
  {
    q: "What exactly does the Supporter money buy today?",
    a: "Nothing yet, because nothing is sold yet. The tier is a free waitlist until every item on its card exists; the day it opens, those items are delivered through Polar.",
  },
  {
    q: "Is Founding Supporter a pre-order?",
    a: "No. Future features are a bonus labelled “in development”, not the thing sold.",
  },
  {
    q: "Why is Setup on Stripe and Supporter on Polar?",
    a: "Polar is the merchant of record for digital goods; it does not allow human services, so services and pilots run on Stripe.",
  },
  {
    q: "Can my company just sponsor the project?",
    a: "GitHub Sponsors. We don't sell sponsorship on Polar.",
  },
  {
    q: "Refunds?",
    a: "Setup and pilots: full refund if the written outcome is not reached. Supporter: 14 days, no questions.",
  },
  {
    q: "Has a third party reviewed this?",
    a: 'No third-party audit yet. Read <a href="/security/#scope">the scope statement</a> and, once it ships, run the bypass script.',
  },
  {
    q: "Windows?",
    a: "Source install only; agent processes fail closed until you opt in.",
  },
];
