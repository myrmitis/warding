import type { APIRoute, GetStaticPaths } from "astro";
import { getCollection } from "astro:content";
import { renderOg, defaultQualifier } from "../../lib/og";
import { staticOgPages } from "../../lib/og-pages";

/**
 * One PNG per page at build: the static registry plus every collection entry
 * (compare-<id>, guides-<id>, channels-<id>). The structure test asserts each
 * page's og:image exists on disk, so a static page must be in og-pages.ts.
 */
export const getStaticPaths = (async () => {
  const [compare, guides, channels] = await Promise.all([getCollection("compare"), getCollection("guides"), getCollection("channels")]);
  const fromCollection = (prefix: string, entries: { id: string; data: { h1: string; ogQualifier: string; ogRegister: "paper" | "night"; draft: boolean } }[]) =>
    entries.filter((e) => !e.data.draft).map((e) => ({ params: { slug: `${prefix}-${e.id}` }, props: { h1: e.data.h1, qualifier: e.data.ogQualifier || defaultQualifier, register: e.data.ogRegister } }));
  return [
    ...staticOgPages.map((p) => ({ params: { slug: p.slug }, props: { h1: p.h1, qualifier: p.qualifier, register: p.register } })),
    ...fromCollection("compare", compare),
    ...fromCollection("guides", guides),
    ...fromCollection("channels", channels),
  ];
}) satisfies GetStaticPaths;

export const GET: APIRoute = async ({ props }) => {
  const png = await renderOg({ h1: props.h1 as string, qualifier: props.qualifier as string, register: props.register as "paper" | "night" });
  return new Response(png as BodyInit, { headers: { "Content-Type": "image/png" } });
};
