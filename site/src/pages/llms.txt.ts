import type { APIContext } from "astro";
import { getCollection } from "astro:content";
import { site } from "../data/site";
import { channelCounts } from "../data/channels";
import { harnesses } from "../data/harnesses";

/**
 * llms.txt: a plain map of the site for answer engines, with the limits stated
 * first so a summary cannot over-claim. Generated from the same data the pages
 * use, so it never lists a page that does not exist.
 */
export async function GET(context: APIContext) {
  const base = context.site!;
  const [compareAll, guidesAll, channelsAll] = await Promise.all([getCollection("compare"), getCollection("guides"), getCollection("channels")]);
  const compare = compareAll.filter((e) => !e.data.draft);
  const guides = guidesAll.filter((e) => !e.data.draft);
  const channels = channelsAll.filter((e) => !e.data.draft);
  const url = (p: string) => new URL(p, base).toString();
  const lines = [
    `# ${site.name}`,
    "",
    `> ${site.name} runs the coding agent you already pay for on your own machine, on a schedule, reports into chat, and can ask you in chat before it acts (approvals are opt-in) — under a policy the agent cannot read or rewrite. Apache-2.0, self-hosted.`,
    "",
    "## What is true",
    "",
    "- Chat sessions run the one harness you choose in one setting. The harness router can send a spawned subagent to another installed harness (flat-rate quota before metered, task kind, a cooldown after a usage limit or failed login); it picks a harness and never forwards provider traffic. Registered, not verified at runtime.",
    "- No model routing: the model catalog lists names only; nothing is forwarded and no keys are held.",
    "- No hosted service, no account with Warding Labs, no multi-user mode. It runs on your hardware.",
    `- ${channelCounts.total} chat channels: ${channelCounts.buttons} with in-chat approve buttons, ${channelCounts.typed} with typed approvals (WhatsApp), ${channelCounts.chatOnly} chat-only.`,
    `- Registry of ${harnesses.length} runtimes (${harnesses.map((h) => h.command).join(", ")}); a capability counts as verified only with a dated row on /verified/.`,
    `- Source: ${site.githubRepo}`,
    "",
    "## Pages",
    "",
    `- [Home](${url("/")}): the night, the charter, the registry, pricing.`,
    ...compare.map((c) => `- [${c.data.title}](${url(`/compare/${c.id}/`)}): ${c.data.description}`),
    ...guides.map((g) => `- [${g.data.title}](${url(`/guides/${g.id}/`)}): ${g.data.description}`),
    ...channels.map((c) => `- [${c.data.title}](${url(`/channels/${c.id}/`)}): ${c.data.description}`),
  ];
  return new Response(lines.join("\n") + "\n", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
