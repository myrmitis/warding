// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import tailwindcss from "@tailwindcss/vite";
import { site } from "./src/data/site.ts";

export default defineConfig({
  // The canonical host comes from one place: src/data/site.ts. The owner flips
  // `domain` there when the new domain is live; nothing else hardcodes it.
  site: site.domain,
  output: "static",
  // Astro 7 defaults to "jsx" whitespace rules, which glue words across line
  // breaks between inline elements. HTML rules keep prose spacing intact.
  compressHTML: true,
  trailingSlash: "always",
  integrations: [react(), mdx(), sitemap()],
  vite: { plugins: [tailwindcss()] },
});
