// Website copy revised by Myrmitis on 2026-10-08; inherited legal attribution preserved in NOTICE.
import type { OgPage } from "../og-pages";

/** OG cards for the revenue and proof pages: pricing, supporters, about, lineage, changelog, verified, registry. */
export const pages: OgPage[] = [
  { slug: "pricing", h1: "Free, all night.", qualifier: "Free forever on your machine · Supporter · Setup · free waitlists", register: "paper" },
  { slug: "supporters", h1: "Founding Supporters", qualifier: "Opt-in names and seal numbers · none yet", register: "paper" },
  { slug: "about", h1: "About", qualifier: "One person, one fork, one rule: say what is true", register: "paper" },
  { slug: "lineage", h1: "Where it comes from", qualifier: "Inherited code, required notices and Warding's changes", register: "paper" },
  { slug: "changelog", h1: "Changelog", qualifier: "Shipped releases only, parsed from the repository", register: "paper" },
  { slug: "verified", h1: "The verification log", qualifier: "Every checkmark links to a dated row", register: "night" },
  { slug: "registry", h1: "The dock registry", qualifier: "Eleven runtimes · one chosen for chat · checks only with a dated row", register: "paper" },
];
