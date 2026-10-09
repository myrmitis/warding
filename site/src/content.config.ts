import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

/**
 * Content collections for the phase-2 page agents. A bad frontmatter field
 * fails `astro build`, and the forbidden-claims suite fails `npm test`, so an
 * agent can only add pages that are structurally and factually in bounds.
 *
 * Shared fields:
 *   title        SEO <title>, ≤ 60 chars
 *   description  meta description, ≤ 155 chars
 *   h1           the page's one H1 (may differ from the title)
 *   ogRegister   "paper" (default) or "night" OG template (brand-book §14)
 *   verified     rows the page's checkmarks point at; each needs a date
 */
const verifiedRow = z.object({
  harness: z.string(),
  feature: z.string(),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "ISO date, YYYY-MM-DD"),
  machine: z.string().default(""),
  log: z.string().url().or(z.literal("")).default(""),
});

const page = {
  title: z.string().max(60),
  description: z.string().max(155),
  h1: z.string(),
  ogRegister: z.enum(["paper", "night"]).default("paper"),
  ogQualifier: z.string().max(90).default(""),
  verified: z.array(verifiedRow).default([]),
  updated: z.coerce.date().optional(),
  draft: z.boolean().default(false),
};

const compare = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/compare" }),
  schema: z.object({
    ...page,
    competitor: z.string(),
    /** Primary sources only; each row on the page cites one. */
    sources: z.array(z.object({ label: z.string(), url: z.string().url() })).default([]),
  }),
});

const guides = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/guides" }),
  schema: z.object({
    ...page,
    author: z.string(),
    published: z.coerce.date(),
    harness: z.string().default(""),
  }),
});

const channelsCollection = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/channels" }),
  schema: z.object({
    ...page,
    channel: z.enum([
      "slack", "discord", "telegram", "teams", "webex", "whatsapp", "imessage", "wechat", "wecom", "feishu",
    ]),
    approval: z.enum(["buttons", "typed", "chat-only"]),
  }),
});

export const collections = { compare, guides, channels: channelsCollection };
