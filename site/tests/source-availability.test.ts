import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { pages, DIST, visibleText } from "./helpers";
import { site } from "../src/data/site";

describe("public source availability", () => {
  it("does not offer a private repository as a public link or download", () => {
    if (site.sourceAvailable) return;
    for (const page of pages) {
      expect(page.html).not.toMatch(/(?:href|action)="https:\/\/github\.com\/myrmitis\/warding/);
      expect(page.html).not.toMatch(/"downloadUrl"/);
      expect(visibleText(page.html)).not.toMatch(/git clone https:\/\/github\.com\/myrmitis\/warding/);
    }
  });
  it("names the public installation limit where visitors start", () => {
    if (site.sourceAvailable) return;
    for (const name of ["index.html", "source/index.html", "quickstart/index.html"]) {
      const page = pages.find((page) => page.name === name);
      expect(page, name).toBeDefined();
      expect(visibleText(page!.html)).toMatch(/publication.*pending/i);
    }
  });
  it("serves mandatory NOTICE and LICENSE byte-identically to the preserved source", () => {
    for (const [served, root] of [["notice.txt", "NOTICE"], ["license.txt", "LICENSE"]]) {
      expect(readFileSync(resolve(DIST, served))).toEqual(readFileSync(resolve("..", root)));
    }
  });
});
