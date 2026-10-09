/**
 * OG image registry. Every prerendered page has a PNG at /og/<slug>.png; the
 * structure test asserts the file exists on disk. Collection entries register
 * themselves (see pages/og/[...slug].png.ts); static pages register here.
 *
 * Slug rule: "/" -> "home"; "/compare/paseo/" -> "compare-paseo"; "/404" -> "404".
 */
export interface OgPage {
  slug: string;
  h1: string;
  qualifier: string;
  register: "paper" | "night";
}

// Page groups register their static pages in src/lib/og-pages/<group>.ts
// (each exporting `pages: OgPage[]`), so several people can add pages without
// editing one shared list.
const groups = import.meta.glob<{ pages: OgPage[] }>("./og-pages/*.ts", { eager: true });

export const staticOgPages: OgPage[] = [
  { slug: "home", h1: "One agent, all night, on your own box.", qualifier: "Claude Code, Codex, Goose, OpenCode or kiro-cli · the one you choose", register: "night" },
  { slug: "404", h1: "That page is not on this floor.", qualifier: "The lamp is on. The page is not.", register: "night" },
  { slug: "compare", h1: "Compare", qualifier: "Fair comparisons, the other tool's strengths first", register: "paper" },
  { slug: "guides", h1: "Guides", qualifier: "Step by step, with the harness and date named", register: "paper" },
  { slug: "channels", h1: "Reach it from the chat you already use.", qualifier: "Five with buttons · one typed · four chat-only", register: "paper" },
  ...Object.values(groups).flatMap((m) => m.pages),
];

export function ogSlugForPath(pathname: string): string {
  const clean = pathname.replace(/^\/+|\/+$/g, "");
  if (clean === "" || clean === "index.html") return "home";
  return clean.replace(/\.html$/, "").replace(/\//g, "-");
}
