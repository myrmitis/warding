import { site } from "./site";

/**
 * The seven offers (site-spec §3). Every item carries exactly one of the three
 * labels docs/business/pricing.md allows — Available now / Pre-order /
 * Waitlist — so an offer whose checkout link is unset is a free waitlist, not
 * an "opens soon" state. `rail` names where the money goes: Polar for digital
 * goods, Stripe for services, GitHub for tips.
 */
export type OfferStatus = "available" | "preorder" | "waitlist" | "opens" | "conversation";
export type Rail = "none" | "polar" | "stripe" | "github" | "waitlist";

export interface Offer {
  id: string;
  name: string;
  price: string;
  priceNote?: string;
  status: OfferStatus;
  /** Rendered label. */
  label: string;
  rail: Rail;
  blurb: string;
  cta: string;
  /** Link from site.ts; "" renders the named coming-soon state. */
  href: string;
  /** Hidden entirely when its link is unset. */
  hiddenWhenUnset?: boolean;
  /** Shown on the homepage preview (four cards). */
  preview: boolean;
  recommended?: boolean;
  /** Waitlist list name for the WaitlistForm island. */
  list?: string;
}

const supporterOpen = site.links.supporterCheckout !== "";
const setupOpen = site.links.setupPayment !== "";

export const offers: Offer[] = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    priceNote: "forever",
    status: "available",
    label: "Available now",
    rail: "none",
    blurb:
      "Dock the harness you choose for chat, with subagents routable to another; schedules; task runner; subagents; memory, lessons, skills; ten chat channels (five with approve buttons); OS sandbox, deny rules, keystone policy, credential redaction, hash-chained audit log; Agent Worlds; 21 apps; 18 themes; 12 languages.",
    cta: site.installOneLiner ? "Copy the install command" : "Copy the quickstart",
    href: "#install",
    preview: true,
    recommended: true,
  },
  {
    id: "supporter",
    name: "Founding Supporter",
    price: "$96/yr",
    priceNote: "price locked while active · or $8/mo",
    status: supporterOpen ? "available" : "waitlist",
    label: supporterOpen ? "Available now" : "Waitlist (free)",
    rail: supporterOpen ? "polar" : "waitlist",
    blurb:
      "A numbered seal badge in your dashboard and, if you opt in, on the Supporters wall; The Vault Agent World scene; the Charter Paper and Warding Night theme pack; a Discord role; a roadmap vote. None of it exists yet, so nothing is sold: the tier opens when every item on this card ships. Future paid features are added to your key as they ship and are labelled 'in development' — they are not what you are buying.",
    cta: "Become a Founding Supporter",
    href: site.links.supporterCheckout,
    preview: true,
  },
  {
    id: "setup",
    name: "Late Desk Setup",
    price: "$199",
    priceNote: "one-time",
    status: setupOpen ? "available" : "waitlist",
    label: setupOpen ? "Available now" : "Waitlist (free)",
    rail: setupOpen ? "stripe" : "waitlist",
    blurb:
      "Sixty minutes on your Mac mini or Linux box: install as a service, dock kiro-cli or Claude Code, connect one channel with buttons, write your first policy profile, run one scheduled job. Scope in writing; full refund if we don't get there.",
    cta: "Book a setup",
    href: site.links.setupPayment,
    preview: true,
    list: "setup",
  },
  {
    id: "pilot",
    name: "Design-Partner Pilot",
    price: "from $1,500",
    priceNote: "60 days",
    status: "conversation",
    label: "Available now · by conversation",
    rail: "stripe",
    blurb:
      "For platform and security leads. Preconditions we meet before you pay: the bypass script, an exportable verified audit chain, the fail-open/fail-closed scope statement, a default build that contacts no server of ours, three recorded overnight runs.",
    cta: "Book a call",
    href: site.links.pilotPage,
    hiddenWhenUnset: true,
    preview: false,
  },
  {
    id: "team",
    name: "Team",
    price: "$24/user/mo",
    priceNote: "annual · $29 monthly · min 3",
    status: "waitlist",
    label: "Waitlist (free)",
    rail: "waitlist",
    blurb:
      "Central policy authoring signed and pushed to every machine, skill and plugin allowlist with a kill switch, audit forwarding to your SIEM, dashboard SSO. Not built yet; built with pilots.",
    cta: "Join the list",
    href: "",
    preview: true,
    list: "team",
  },
  {
    id: "hosted",
    name: "Hosted late desk",
    price: "$49–99/mo",
    priceNote: "target",
    status: "waitlist",
    label: "Waitlist (free)",
    rail: "waitlist",
    blurb:
      "A box we run, your agent subscription. We build it when fifty people say what they'd pay and the memory numbers are measured.",
    cta: "Join the list",
    href: "",
    preview: false,
    list: "hosted",
  },
  {
    id: "tips",
    name: "Tips",
    price: "any",
    status: "available",
    label: "Available now",
    rail: "github",
    blurb: "GitHub Sponsors. Nothing in return but thanks.",
    cta: "Sponsor on GitHub",
    href: site.links.sponsors,
    hiddenWhenUnset: true,
    preview: false,
  },
];

export const previewOffers = offers.filter((o) => o.preview && !(o.hiddenWhenUnset && o.href === ""));
