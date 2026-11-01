import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The repository's CHANGELOG.md, parsed at build for /changelog/ with the
 * same rules as the product's own parser (`src/junction/changelog.py`):
 * only `## [X.Y.Z] — YYYY-MM-DD` sections count, any other level-2 heading
 * closes the section above it (so an Unreleased section is never swallowed
 * and never listed), a prerelease spelling folds onto its base version, and
 * the first section for a version in document order wins.
 *
 * The tree carries the upstream project's release notes up to
 * `INHERITED_THROUGH`; they describe upstream's releases, so the page lists
 * their versions and dates and links the file rather than reproducing them.
 * Sections above that version are this product's own and render in full.
 */
export interface ChangelogSection {
  version: string;
  date: string;
  body: string;
  html: string;
  /** True when the section is this product's own release. */
  own: boolean;
}

/** The last upstream release whose notes travel with the tree, unedited. */
export const INHERITED_THROUGH = "0.4.0";

const SECTION_RE = /^##\s+\[([^\]]+)\](?:\s*[—–-]\s*(\d{4}-\d{2}-\d{2}))?\s*$/;
const H2_RE = /^##\s+\S/;
const BASE_RE = /^(\d+(?:\.\d+)*)(?:-(?:rc|insider|alpha|beta)\.\d+|-nightly\.\d{8}(?:t\d{6}|\d{4})?|(?:a|b|c|rc)\d+(?:\.post\d+)?(?:\.dev\d+)?|\.post\d+(?:\.dev\d+)?|\.dev\d+)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/;

export function baseVersion(version: string): string {
  const m = BASE_RE.exec(version.trim());
  return m ? m[1] : version.trim();
}

function versionKey(v: string): number[] {
  return v.split(".").map((s) => (/^\d+$/.test(s) ? Number(s) : -1));
}

export function compareVersions(a: string, b: string): number {
  const ka = versionKey(a);
  const kb = versionKey(b);
  for (let i = 0; i < Math.max(ka.length, kb.length); i++) {
    const d = (ka[i] ?? 0) - (kb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

/** Split markdown into (version, date, body) per shipped heading, in document order. */
export function parseSections(markdown: string): { version: string; date: string; body: string }[] {
  const out: { version: string; date: string; body: string }[] = [];
  let version = "";
  let date = "";
  let body: string[] = [];
  let open = false;
  const flush = () => {
    if (open) out.push({ version, date, body: body.join("\n").trim() });
  };
  for (const line of markdown.split(/\r?\n/)) {
    const m = SECTION_RE.exec(line);
    if (m) {
      flush();
      version = m[1].trim();
      date = m[2] ?? "";
      body = [];
      open = true;
      continue;
    }
    if (open && H2_RE.test(line)) {
      flush();
      open = false;
      continue;
    }
    if (open) body.push(line);
  }
  flush();
  return out;
}

/* ---------------------------------------------------------------------------
   A minimal markdown renderer for the shapes the changelog format allows
   (headings, bullets, paragraphs, bold, code, links). Every character of the
   source is entity-escaped before any tag is added, so nothing in the file
   can inject markup; links are emitted only for http(s) and site-relative
   targets.
   --------------------------------------------------------------------------- */
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inline(escaped: string): string {
  let s = escaped;
  // Code first, so nothing inside a span is treated as markup.
  const codes: string[] = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c: string) => {
    codes.push(`<code>${c}</code>`);
    return `\u0000${codes.length - 1}\u0000`;
  });
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (whole, text: string, href: string) => {
    if (/^https?:\/\//.test(href)) return `<a href="${href}" rel="noopener">${text}</a>`;
    if (/^\/[^/]/.test(href)) return `<a href="${href}">${text}</a>`;
    return whole;
  });
  return s.replace(/\u0000(\d+)\u0000/g, (_, i: string) => codes[Number(i)]);
}

export function renderMarkdown(markdown: string): string {
  const out: string[] = [];
  let para: string[] = [];
  let items: string[] = [];
  const closePara = () => {
    if (para.length) out.push(`<p>${inline(para.join(" "))}</p>`);
    para = [];
  };
  const closeList = () => {
    if (items.length) out.push(`<ul>${items.map((i) => `<li>${inline(i)}</li>`).join("")}</ul>`);
    items = [];
  };
  for (const raw of markdown.split(/\r?\n/)) {
    const line = escapeHtml(raw.replace(/\s+$/, ""));
    if (line.trim() === "") {
      closePara();
      closeList();
      continue;
    }
    const heading = /^(#{3,4})\s+(.+)$/.exec(line);
    if (heading) {
      closePara();
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
    if (bullet) {
      closePara();
      items.push(bullet[1]);
      continue;
    }
    if (items.length && /^\s+\S/.test(line)) {
      items[items.length - 1] += ` ${line.trim()}`;
      continue;
    }
    closeList();
    para.push(line.trim());
  }
  closePara();
  closeList();
  return out.join("\n");
}

/** Shipped sections, newest first, deduplicated onto their base version. */
export function loadChangelog(path = resolve(process.cwd(), "..", "CHANGELOG.md")): ChangelogSection[] {
  let text = "";
  try {
    text = readFileSync(path, "utf8");
  } catch {
    return [];
  }
  const byBase = new Map<string, ChangelogSection>();
  for (const s of parseSections(text)) {
    const key = baseVersion(s.version);
    if (byBase.has(key)) continue;
    const own = compareVersions(key, INHERITED_THROUGH) > 0;
    byBase.set(key, { version: key, date: s.date, body: s.body, html: own ? renderMarkdown(s.body) : "", own });
  }
  return [...byBase.values()].sort((a, b) => compareVersions(b.version, a.version));
}
