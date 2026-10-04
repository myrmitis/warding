import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DIST, pages, decode } from "./helpers";

/**
 * Internal links over dist/: every root-relative href must resolve to a file
 * the build wrote, and every in-page fragment to an id on that page.
 *
 * SITE_LINKCHECK_STRICT (default on) gates the file check. Inner pages land in
 * parallel with the homepage, so a local run can set SITE_LINKCHECK_STRICT=0
 * to see the rest of the suite while they are missing; CI keeps it on.
 */
const strict = (process.env.SITE_LINKCHECK_STRICT ?? "1") !== "0";

const hrefs = (html: string) => Array.from(html.matchAll(/<a\b[^>]*\shref="([^"]*)"/gi), (m) => decode(m[1]));
const ids = (html: string) => new Set(Array.from(html.matchAll(/\sid="([^"]*)"/gi), (m) => decode(m[1])));

/** The dist file a root-relative path is served from, or null. */
function resolveDist(pathname: string): string | null {
  const clean = decodeURIComponent(pathname);
  const candidates = clean.endsWith("/")
    ? [join(DIST, clean, "index.html")]
    : [join(DIST, clean), join(DIST, `${clean}.html`), join(DIST, clean, "index.html")];
  for (const c of candidates) if (existsSync(c) && statSync(c).isFile()) return c;
  return null;
}

describe("internal links", () => {
  it.skipIf(!strict)("every root-relative href resolves to a file in dist/", () => {
    const missing = new Map<string, Set<string>>();
    for (const page of pages) {
      for (const href of hrefs(page.html)) {
        if (!href.startsWith("/") || href.startsWith("//")) continue;
        const path = href.split(/[?#]/)[0] || "/";
        if (resolveDist(path)) continue;
        if (!missing.has(path)) missing.set(path, new Set());
        missing.get(path)!.add(page.name);
      }
    }
    const report = Array.from(missing.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([path, from]) => `${path}  <- ${Array.from(from).sort().join(", ")}`);
    expect(report, `missing internal pages:\n${report.join("\n")}`).toEqual([]);
  });

  for (const page of pages) {
    it(`${page.name}: every in-page #fragment names an id on the page`, () => {
      const known = ids(page.html);
      const bad = hrefs(page.html)
        .filter((h) => h.startsWith("#") && h.length > 1)
        .filter((h) => !known.has(h.slice(1)));
      expect(bad).toEqual([]);
    });
  }
});
