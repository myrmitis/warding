// Website copy revised by Myrmitis on 2026-10-08; inherited legal attribution preserved in NOTICE.
import { site } from "./site";

export interface NavLink {
  label: string;
  href: string;
  external?: boolean;
}

/** Centre nav (site-spec §2.0). Docs is the repo's docs tree; there is no /docs/ page. */
export const primaryNav: NavLink[] = [
  { label: "Product", href: "/#product" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "Beta notes", href: "/verified/" },
  { label: "Setup notes", href: "/quickstart/" },
];

export const footerColumns: { title: string; links: NavLink[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Security", href: "/security/" },
      { label: "Approvals", href: "/approvals/" },
      { label: "Channels", href: "/channels/" },
      { label: "Schedule", href: "/schedule/" },
      { label: "Agent Worlds", href: "/agent-worlds/" },
      { label: "Registry", href: "/registry/" },
      { label: "Verified", href: "/verified/" },
    ],
  },
  {
    title: "Compare",
    links: [
      { label: "Upstream", href: "/compare/upstream/" },
      { label: "OpenClaw", href: "/compare/openclaw/" },
      { label: "Claude Code Routines", href: "/compare/claude-code-routines/" },
      { label: "Paseo", href: "/compare/paseo/" },
    ],
  },
  {
    title: "Learn",
    links: [
      { label: "Quickstart", href: "/quickstart/" },
      { label: "Guides", href: "/guides/" },
      { label: "Setup notes", href: "/quickstart/" },
      { label: "Changelog", href: "/changelog/" },
      { label: "Lineage", href: "/lineage/" },
      { label: "About", href: "/about/" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Pricing", href: "/pricing/" },
      { label: "Supporters", href: "/supporters/" },
      { label: "Security reporting", href: site.links.securityMd },
      { label: "Privacy", href: "/privacy/" },
      { label: "Terms", href: "/terms/" },
      { label: "Contact status", href: "/about/#contact-h" },
    ],
  },
];
