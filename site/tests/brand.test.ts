import { describe, expect, it } from "vitest";
import { pages, visibleText } from "./helpers";
import { site } from "../src/data/site";

/**
 * Brand hygiene over dist/: the product name is present on every page; no
 * implementation leak (ports, old data-home paths); the retired brand token is
 * absent in every spelling.
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
      it("carries the retired brand in no spelling, anywhere in the markup", () => {
        expect(page.html).not.toMatch(new RegExp("ki" + "ro" + "[\\s_-]*" + "cr" + "ew", "i"));
        expect(page.html).not.toMatch(new RegExp("ki" + "ro" + "dot" + "dev", "i"));
      });
      it("uses no Google Fonts", () => {
        expect(page.html).not.toMatch(/fonts\.googleapis|fonts\.gstatic/);
      });
    });
  }
});
