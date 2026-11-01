import { describe, expect, it } from "vitest";
import { pages, visibleText, withoutAliases } from "./helpers";
import { site } from "../src/data/site";

/**
 * Brand hygiene over dist/: the product name is present on every page; no
 * implementation leak (ports, old data-home paths); the upstream brand token is
 * absent in every spelling; "Junction" as a product name appears in no visible
 * text — only as the package/CLI alias inside `data-alias` elements and in the
 * GitHub URL.
 */
describe("brand", () => {
  for (const page of pages) {
    describe(page.name, () => {
      const text = visibleText(page.html);

      it(`names ${site.name}`, () => {
        expect(text).toMatch(new RegExp(`\\b${site.name}\\b`));
      });
      it("leaks no local port or old data-home path", () => {
        expect(page.html).not.toMatch(/localhost:5476/);
        expect(page.html).not.toMatch(new RegExp("~/\\." + "ki" + "ro" + "/" + "cr" + "ew"));
        expect(page.html).not.toMatch(new RegExp("\\." + "ki" + "ro" + "cr" + "ew" + "\\b"));
      });
      it("carries the upstream brand in no spelling, anywhere in the markup", () => {
        expect(page.html).not.toMatch(new RegExp("ki" + "ro" + "[\\s_-]*" + "cr" + "ew", "i"));
        expect(page.html).not.toMatch(new RegExp("ki" + "ro" + "dot" + "dev", "i"));
      });
      it("uses 'Junction' as a product name in no visible text", () => {
        const stripped = withoutAliases(page.html).replace(/\s(?:href|src|action)="[^"]*"/g, "");
        const vis = visibleText(stripped);
        const m = vis.match(/\bJunction\b/);
        expect(m ? `"Junction" at …${vis.slice(Math.max(0, (m.index ?? 0) - 60), (m.index ?? 0) + 60)}…` : null).toBeNull();
      });
      it("uses no Google Fonts", () => {
        expect(page.html).not.toMatch(/fonts\.googleapis|fonts\.gstatic/);
      });
    });
  }
});
