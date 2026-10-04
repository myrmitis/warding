/**
 * Owner-configurable site object (site-spec §9). One object, one place.
 *
 * Every consumer of a link checks for `""` and renders the named "coming soon"
 * state (a disabled button with visible text, or nothing) — never an `href=""`,
 * never `#`, never a 404. The build tests enforce that on `dist/`.
 */
export const site = {
  name: "Warding",
  company: "Warding Labs",
  // The owner flips this to "https://warding.dev" once that domain is bought and
  // live; getjunction.dev is the host that serves today. Every canonical URL,
  // OG image URL, sitemap entry and the footer domain text derive from it.
  domain: "https://getjunction.dev",
  githubRepo: "https://github.com/laqaer/junction", // owner updates after the rename
  version: "0.5.0", // pyproject version; shown next to the install command
  nightsVerified: false, // flips [pre] -> [post] copy; the claims test enforces it
  installOneLiner: "", // "" -> quickstart tabs + "Copy the quickstart"
  tagline: "The lamp stays on. The rules stay shut.",
  taglineShort: "The lamp stays on.",
  cli: "warding",
  cliAlias: "junction",
  links: {
    supporterCheckout: "", // Polar checkout link; "" -> "Opens November", disabled, aria-disabled
    supporterMonthly: "", // Polar monthly link
    setupPayment: "", // Stripe Payment Link; "" -> "Setup opens soon" + email capture instead
    pilotPage: "", // "" -> pilot card hidden entirely
    calendar: "", // Cal.com URL; "" -> "Calls open soon" text, no link
    sponsors: "", // GitHub Sponsors; "" -> tips card hidden
    discord: "",
    discussions: "",
    telegramGroup: "", // "" -> that footer link hidden
    securityMd: "https://github.com/laqaer/junction/blob/main/SECURITY.md",
  },
  waitlist: {
    endpoint: "", // POST JSON {email, list, answers}; "" -> fallback chain (site-spec §10)
    mailto: "", // "" -> next fallback
    discussionUrl: "", // GitHub Discussion "Waitlists" thread; "" -> final fallback
  },
  analytics: {
    provider: "", // "plausible" | "umami" | ""; "" -> no script injected, events no-op
    domain: "",
    scriptSrc: "",
  },
  // Feature flags for copy that is labelled in development until the linked backlog item ships.
  shipped: {
    dawnGrants: false, // "Allow until 07:00" without "in development"
    charterCommand: false, // `warding charter` without the in-development label
    morningReport: false, // Morning Report card with counts
  },
} as const;

export type Site = typeof site;

/** Bare host for footer text and OG cards, derived from `site.domain`. */
export const siteHost = new URL(site.domain).host;
