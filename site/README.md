# Warding marketing site

Astro 7 static site (React islands only where interaction needs them), served by
Vercel from this directory. Every page is prerendered HTML.

```bash
npm ci
npm run dev          # astro dev
npm run build        # astro check && astro build  -> dist/
npm test             # builds, then runs the dist/ suites
```

Node ≥ 22.12. All dependencies are `devDependencies` (nothing ships at runtime).

## Where things live

| Path | What |
|---|---|
| `src/data/site.ts` | The one config object: domain, repo, publisher, version, feature flags, checkout and waitlist links. The publisher supplies the linked "by Myrmitis" attribution in the header and footer and the website/software JSON-LD. `""` renders a named "coming soon" state, never a broken link. The owner flips `domain` when the new one is live. |
| `src/data/channels.ts`, `harnesses.ts`, `pricing.ts`, `nav.ts` | The ten channels with their honest approval mode, the eleven runtimes with verified flags and the harness router, the seven offers with labels and rails, the nav and footer. Pages read these; do not restate the facts in copy. |
| `src/content/{compare,guides,channels}/*.mdx` | Content collections. Frontmatter is schema-validated (`src/content.config.ts`): `title` ≤ 60, `description` ≤ 155, `h1`, `ogRegister`, `verified` rows with ISO dates. A bad field fails the build. |
| `src/layouts/BaseLayout.astro` | Head (title, description, canonical, OG/Twitter, theme-color both schemes, JSON-LD slot), skip link, landmarks, reveal script. |
| `src/layouts/PageLayout.astro` | Inner pages: `{title, description, h1, register, breadcrumbs, lead}`. |
| `src/components/` | Astro, zero-JS: `Nav`, `Footer`, `WardSeal`, `WardBars`, `StatusChip` (icon + word, never colour-only), `Plate` (a `figure[data-shot]` whose caption must carry harness + date), `PhoneCard`, `CharterSheet`, `ClockHead`, `Button`, `LinkButton`, `FaqItem`. |
| `src/islands/` | React: `InstallTabs`, `ApproveFromChatDemo`, `WaitlistForm` (fallback chain of site-spec §10), `world/OfficeWorld` (the product's Office renderer, ported as a pure module in `world/office.ts`), `world/Drollery`. |
| `src/lib/og.ts` + `src/pages/og/[...slug].png.ts` | Build-time OG PNGs (satori + resvg). Collection entries get one automatically; a static page must be listed in `src/lib/og-pages.ts`. |
| `src/assets/shots/` | Real dashboard captures, same filenames as the capture manifest so they can be overwritten in place. Compressed to AVIF/WebP at build by `<Plate>`. |
| `public/fonts/` | Departure Mono (OFL, licence alongside). Fraunces, IBM Plex Sans and IBM Plex Mono come from Fontsource. No Google Fonts. |
| `tests/` | `claims.test.ts` (the forbidden-claims list), `structure.test.ts` (head tags, landmarks, sitemap, robots, alt text, pause controls), `brand.test.ts`. They run over `dist/`. |

## Adding a page

1. Prefer a collection entry: drop `src/content/<collection>/<slug>.mdx` with the
   schema's frontmatter. Route, sitemap entry, OG image and `llms.txt` line appear
   automatically.
2. For a static page, use `PageLayout`, add the page to `src/lib/og-pages.ts`
   (slug rule: `/compare/paseo/` → `compare-paseo`), and keep the title ≤ 60 and
   description ≤ 155 (the layout throws otherwise).
3. Status is icon + word (`StatusChip`), never colour alone. Every screenshot goes
   through `<Plate>` with the manifest caption. Links from `site.ts` that are `""`
   render their coming-soon state.
4. Run `npm test`. The claims suite is the honesty gate: every phrase in
   site-spec §11 fails the build, including the retired product's two-word name in
   any spelling.

## Theme mechanics

Tokens live on `:root` (paper), are redefined under
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`,
again under `:root[data-theme="dark"]`, and locally inside any `.vault` wrapper
(night sections on a paper page). The toggle persists to `localStorage`
(`warding.theme`) inside try/catch.
