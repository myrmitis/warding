import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { getCollection } from "astro:content";
import { site } from "../data/site";

/**
 * Releases and guides feed. Empty-safe: with no shipped release section and no
 * guides yet, the feed is a valid channel with zero items. The changelog page
 * (phase 2) adds one item per shipped `## [X.Y.Z]` section.
 */
export async function GET(context: APIContext) {
  const guides = await getCollection("guides");
  return rss({
    title: `${site.name} releases and guides`,
    description: "Shipped releases and new guides. Nothing else.",
    site: context.site!,
    items: guides
      .filter((g) => !g.data.draft)
      .map((g) => ({ title: g.data.title, description: g.data.description, pubDate: g.data.published, link: `/guides/${g.id}/` })),
    customData: "<language>en</language>",
  });
}
