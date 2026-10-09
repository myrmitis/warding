import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DIST, pages, decode } from "./helpers";
import { site } from "../src/data/site";

const attr = (html: string, re: RegExp) => {
  const m = html.match(re);
  return m ? decode(m[1]) : null;
};

function allFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...allFiles(p));
    else out.push(p);
  }
  return out;
}

describe("structure (site-spec §11)", () => {
  for (const page of pages) {
    describe(page.name, () => {
      const { html } = page;
      const is404 = page.name === "404.html";

      it("has exactly one <h1>", () => {
        expect(html.match(/<h1\b/gi)?.length ?? 0).toBe(1);
      });
      it("has a <title> of at most 60 characters", () => {
        const t = attr(html, /<title>([^<]*)<\/title>/i);
        expect(t).toBeTruthy();
        expect(t!.length).toBeLessThanOrEqual(60);
      });
      it("has a meta description of at most 155 characters", () => {
        const d = attr(html, /<meta name="description" content="([^"]*)"/i);
        expect(d).toBeTruthy();
        expect(d!.length).toBeLessThanOrEqual(155);
      });
      it("has an absolute, self-referencing canonical", () => {
        const c = attr(html, /<link rel="canonical" href="([^"]*)"/i);
        expect(c).toBeTruthy();
        expect(c!.startsWith(site.domain + "/")).toBe(true);
        if (!is404) {
          const expected = new URL("/" + page.name.replace(/index\.html$/, ""), site.domain).toString();
          expect(c).toBe(expected);
        }
      });
      it("points og:image at a PNG that exists on disk, with alt", () => {
        const og = attr(html, /<meta property="og:image" content="([^"]*)"/i);
        expect(og).toBeTruthy();
        expect(og!.startsWith(site.domain)).toBe(true);
        const p = join(DIST, new URL(og!).pathname);
        expect(existsSync(p), `${og} missing on disk`).toBe(true);
        expect(attr(html, /<meta property="og:image:alt" content="([^"]*)"/i)).toBeTruthy();
        expect(html).toMatch(/<meta name="twitter:card" content="summary_large_image"/);
      });
      it("gives every live canvas a visible Pause control", () => {
        const live = html.match(/\bdata-live\b/g)?.length ?? 0;
        const pause = html.match(/aria-label="Pause"/g)?.length ?? 0;
        expect(pause).toBeGreaterThanOrEqual(live);
      });
      it("gives every <img> a non-empty alt", () => {
        for (const m of html.matchAll(/<img\b[^>]*>/gi)) {
          const a = m[0].match(/\balt="([^"]*)"/);
          expect(a && a[1].trim().length > 0, `img without alt: ${m[0].slice(0, 120)}`).toBe(true);
        }
      });
      it("captions every screenshot figure with a harness and a date", () => {
        for (const m of html.matchAll(/<figure\b[^>]*\bdata-shot\b[\s\S]*?<\/figure>/gi)) {
          const cap = m[0].match(/<figcaption[^>]*>([\s\S]*?)<\/figcaption>/i);
          expect(cap, "figure[data-shot] without figcaption").toBeTruthy();
          const text = decode(cap![1].replace(/<[^>]+>/g, " "));
          expect(text).toMatch(/\d{4}-\d{2}-\d{2}/);
          expect(text).toMatch(/\b(claude|kiro-cli|codex|goose|cursor|kimi|grok|droid|dashboard|cli)\b/i);
        }
      });
      it("has no empty or '#' hrefs", () => {
        expect(html).not.toMatch(/href=""/);
        expect(html).not.toMatch(/href="#"/);
      });
      it("declares the theme-color and scheme of its register", () => {
        // The register fixes the page's scheme (the day/night split is the
        // brand), so the browser chrome matches it rather than the OS setting.
        const night = /<html[^>]*data-register="night"/.test(html);
        expect(html).toMatch(new RegExp(`<meta name="theme-color" content="${night ? "#0B0E14" : "#F3EEE3"}"`, "i"));
        expect(html).toMatch(new RegExp(`<html[^>]*data-theme="${night ? "dark" : "light"}"`));
      });
      it("gives every element a unique id", () => {
        // A repeated id makes fragment links and aria references land on the
        // first match only, e.g. a guide's "## Install" heading and the
        // closing install band both claiming #install. Scripts are skipped:
        // JSON-LD and island props carry "id" keys that are not attributes.
        const markup = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ");
        const ids = [...markup.matchAll(/<[a-z][^>]*?\sid="([^"]+)"/gi)].map((m) => m[1]);
        const dupes = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
        expect(dupes).toEqual([]);
      });
      it("has landmarks and a skip link", () => {
        expect(html).toMatch(/<header\b/);
        expect(html).toMatch(/<main\b[^>]*id="main"/);
        expect(html).toMatch(/<footer\b/);
        expect(html).toMatch(/class="skip-link" href="#main"/);
      });
      it("renders nothing at opacity 0 before JS", () => {
        expect(html).not.toMatch(/style="[^"]*opacity:\s*0[;"]/);
      });
    });
  }

  it("sitemap lists every page (except 404)", () => {
    const sm = readFileSync(join(DIST, "sitemap-0.xml"), "utf8");
    const locs = new Set(Array.from(sm.matchAll(/<loc>([^<]+)<\/loc>/g)).map((m) => m[1]));
    for (const page of pages) {
      if (page.name === "404.html") continue;
      const url = new URL("/" + page.name.replace(/index\.html$/, ""), site.domain).toString();
      expect(locs.has(url), `${url} not in sitemap`).toBe(true);
    }
    expect(readFileSync(join(DIST, "sitemap-index.xml"), "utf8")).toContain("sitemap-0.xml");
  });

  it("robots.txt allows all and names the sitemap", () => {
    const r = readFileSync(join(DIST, "robots.txt"), "utf8");
    expect(r).toMatch(/User-agent: \*\s+Allow: \//);
    expect(r).toContain(`Sitemap: ${site.domain}/sitemap-index.xml`);
    expect(r).not.toMatch(/Disallow: \/\s*$/m);
  });

  it("never loads Google Fonts", () => {
    for (const f of allFiles(DIST)) {
      if (!/\.(html|css|js)$/.test(f)) continue;
      const s = readFileSync(f, "utf8");
      expect(s, f).not.toMatch(/fonts\.googleapis|fonts\.gstatic/);
    }
  });

  it("ships llms.txt with the limits stated", () => {
    const t = readFileSync(join(DIST, "llms.txt"), "utf8");
    expect(t).toMatch(/Chat sessions run the one harness you choose/);
    expect(t).toMatch(/never forwards provider traffic/);
    expect(t).toMatch(/No model routing/);
    expect(t).toMatch(/No hosted service/);
    expect(t).toMatch(/Apache-2\.0/);
  });

  it("ships a valid, empty-safe RSS feed", () => {
    const r = readFileSync(join(DIST, "rss.xml"), "utf8");
    expect(r).toMatch(/<rss\b/);
    expect(r).toMatch(/<channel>/);
  });
});
