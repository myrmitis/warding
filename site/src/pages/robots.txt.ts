import type { APIContext } from "astro";

/** Allow all crawlers, including AI crawlers; name the sitemap from site.domain. */
export function GET(context: APIContext) {
  const body = ["User-agent: *", "Allow: /", "", `Sitemap: ${new URL("/sitemap-index.xml", context.site!).toString()}`, ""].join("\n");
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
