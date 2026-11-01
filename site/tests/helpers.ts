import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const DIST = fileURLToPath(new URL("../dist/", import.meta.url));

export function htmlFiles(dir = DIST): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...htmlFiles(p));
    else if (name.endsWith(".html")) out.push(p);
  }
  return out.sort();
}

export const rel = (p: string) => relative(DIST, p);

export const pages = htmlFiles().map((path) => ({ path, name: rel(path), html: readFileSync(path, "utf8") }));

export function decode(s: string): string {
  return s
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
}

/**
 * The text a reader or a crawler sees: visible text, the title, meta content,
 * alt/aria-label/title attributes and JSON-LD. Scripts, styles and anything
 * quoted as a competitor's headline inside <q> are excluded.
 */
export function visibleText(html: string): string {
  let h = html.replace(/<script\b(?![^>]*application\/ld\+json)[^>]*>[\s\S]*?<\/script>/gi, " ");
  h = h.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ");
  h = h.replace(/<q\b[^>]*>[\s\S]*?<\/q>/gi, " ");
  const attrs: string[] = [];
  for (const m of h.matchAll(/\s(?:content|alt|aria-label|title|placeholder)="([^"]*)"/g)) attrs.push(m[1]);
  const text = h.replace(/<[^>]+>/g, " ");
  return decode([text, ...attrs].join("\n")).replace(/\s+/g, " ");
}

export function headings(html: string, levels = [1, 2, 3]): string[] {
  const out: string[] = [];
  for (const l of levels) for (const m of html.matchAll(new RegExp(`<h${l}\\b[^>]*>([\\s\\S]*?)<\\/h${l}>`, "gi"))) out.push(decode(m[1].replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim());
  return out;
}

/** The text of a page with elements carrying `data-alias` removed. */
export function withoutAliases(html: string): string {
  return html.replace(/<(\w+)\b[^>]*\bdata-alias\b[^>]*>[\s\S]*?<\/\1>/gi, " ");
}
