import { site, siteHost } from "./site";

export interface NavLink {
  label: string;
  href: string;
  external?: boolean;
}

/** Centre nav (site-spec §2.0). Docs is the repo's docs tree; there is no /docs/ page. */
export const primaryNav: NavLink[] = [
  { label: "Security", href: "/security/" },
  { label: "Channels", href: "/channels/" },
  { label: "Schedule", href: "/schedule/" },
  { label: "Agent Worlds", href: "/agent-worlds/" },
  { label: "Compare", href: "/compare/" },
  { label: "Pricing", href: "/pricing/" },
  { label: "Docs", href: `${site.githubRepo}/tree/main/docs`, external: true },
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
      { label: "OpenClaw", href: "/compare/openclaw/" },
      { label: "Claude Code Routines", href: "/compare/claude-code-routines/" },
      { label: "Paseo", href: "/compare/paseo/" },
    ],
  },
  {
    title: "Learn",
    links: [
      { label: "Guides", href: "/guides/" },
      { label: "Docs", href: `${site.githubRepo}/tree/main/docs`, external: true },
      { label: "Changelog", href: "/changelog/" },
      { label: "About", href: "/about/" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Pricing", href: "/pricing/" },
      { label: "Supporters", href: "/supporters/" },
      { label: "SECURITY.md", href: site.links.securityMd, external: true },
      { label: "Privacy", href: "/privacy/" },
      { label: "Terms", href: "/terms/" },
      { label: "Contact", href: `mailto:hello@${siteHost}` },
    ],
  },
];
