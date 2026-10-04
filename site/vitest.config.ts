/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

// The suites read the prerendered `dist/` tree: that is the artefact search
// engines and social cards see, so it is the only thing worth asserting on.
export default getViteConfig({
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
