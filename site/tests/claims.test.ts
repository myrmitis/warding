import { describe, expect, it } from "vitest";
import { pages, visibleText, headings } from "./helpers";
import { site } from "../src/data/site";

/**
 * The forbidden-claims gate (site-spec §11), run over the prerendered dist/.
 * Case-insensitive and word-bounded unless a rule says otherwise. Phrases
 * quoted as a competitor's headline inside <q> are exempt (stripped by the
 * text extractor); nothing else is.
 */
const never: [string, RegExp][] = [
  ["side by side", /\bside by side\b/i],
  ["side-by-side", /\bside-by-side\b/i],
  ["parallel harness", /\bparallel harness/i],
  ["route your models", /\broute your models\b/i],
  ["model router", /\bmodel router\b/i],
  ["routes your", /\broutes your\b/i],
  ["cheaper tokens", /\bcheaper tokens\b/i],
  ["pip install junction", /\bpip install junction\b/i],
  ["docker pull", /\bdocker pull\b/i],
  ["desktop app (except 'no desktop app yet')", /(?<!\bno )\bdesktop app\b/i],
  ["signed installer (except 'no signed installers yet')", /(?<!\bno )\bsigned installers?\b/i],
  ["hosted service (except 'no hosted service')", /(?<!\bno )\bhosted service\b/i],
  ["sign up", /\bsign up\b/i],
  ["create an account", /\bcreate an account\b/i],
  ["multi-user", /\bmulti-user\b/i],
  ["teams workspace", /\bteams workspace\b/i],
  ["nothing leaves your machine", /\bnothing leaves your machine\b/i],
  ["works out of the box", /\bworks out of the box\b/i],
  ["10 apps with approvals", /\b(10|ten) apps with (approvals|buttons)\b/i],
  ["unbreakable", /\bunbreakable\b/i],
  ["sealed", /\bsealed\b/i],
  ["physically", /\bphysically\b/i],
  ["route around", /\broute around\b/i],
  ["safe by construction", /\bsafe by construction\b/i],
  ["zero-trust", /\bzero[- ]trust\b/i],
  ["audited (except 'unaudited')", /(?<!un)\baudited\b/i],
  ["certified", /\bcertified\b/i],
  ["ToS-safe", /\btos-safe\b/i],
  ["while you sleep", /\bwhile you sleep\b/i],
  ["autopilot", /\bautopilot\b/i],
  ["control plane", /\bcontrol plane\b/i],
  ["command center", /\bcommand cent(er|re)\b/i],
  ["agent HQ", /\bagent hq\b/i],
  ["orchestrat*", /orchestrat/i],
  ["agentic IDE", /\bagentic ide\b/i],
  ["ADE", /\bADE\b/],
  ["AI teammate", /\bai teammate\b/i],
  ["from anywhere", /\bfrom anywhere\b/i],
  ["in your pocket", /\bin your pocket\b/i],
  ["grows with you", /\bgrows with you\b/i],
  ["learns how you work", /\blearns how you work\b/i],
  ["keep work moving", /\bkeep work moving\b/i],
  ["software factory", /\bsoftware factory\b/i],
  ["autonomous software engineer", /\bautonomous software engineer\b/i],
  ["10X", /\b10x\b/i],
  ["upstream two-word product name, joined or spaced", new RegExp("\\b" + "ki" + "ro" + "[\\s_-]*" + "cr" + "ew" + "\\b", "i")],
  ["upstream GitHub org slug", new RegExp("ki" + "ro" + "dot" + "dev", "i")],
  ["trusted by", /\btrusted by\b/i],
  ["used by + number", /\bused by\s+[\d,.]+k?\b/i],
  ["stars + number", /\b\d[\d,.]*\s*k?\s*stars\b|\bstars\b[^.\n]{0,12}\d/i],
  ["20+ PRs", /\b20\+? PRs\b/i],
  ["10 GB", /\b10 ?GB\b/i],
  ["135k", /\b135k\b/i],
  ["1,184", /\b1,184\b/],
  ["Everything you need", /\beverything you need\b/i],
  ["localhost:5476", /localhost:5476/],
  ["the retired data home", new RegExp("~/\\." + "ki" + "ro" + "/" + "cr" + "ew")],
];
if (!/warding/i.test(site.installOneLiner)) never.push(["pip install warding", /\bpip install warding\b/i]);

const EMOJI = /\p{Emoji_Presentation}|️/u;

describe("forbidden claims (site-spec §11)", () => {
  it("dist/ has pages to check", () => {
    expect(pages.length).toBeGreaterThan(0);
  });

  for (const page of pages) {
    describe(page.name, () => {
      const text = visibleText(page.html);

      for (const [label, re] of never) {
        it(`never says: ${label}`, () => {
          const m = text.match(re);
          expect(m ? `"${label}" found: …${text.slice(Math.max(0, (m.index ?? 0) - 60), (m.index ?? 0) + 60)}…` : null).toBeNull();
        });
      }

      it("has no emoji", () => {
        const m = page.html.match(EMOJI);
        expect(m ? `emoji at …${page.html.slice(Math.max(0, (m.index ?? 0) - 40), (m.index ?? 0) + 40)}…` : null).toBeNull();
      });

      it("never headlines 'any agent'", () => {
        for (const h of headings(page.html)) expect(h).not.toMatch(/\bany agent\b/i);
      });

      it("names Gemini only in a not-docked / not-yet / upstream-has sentence", () => {
        for (const m of text.matchAll(/\b(Gemini)\b/g)) {
          const start = text.lastIndexOf(".", m.index ?? 0) + 1;
          const end = text.indexOf(".", m.index ?? 0);
          const sentence = text.slice(start, end < 0 ? undefined : end + 1);
          expect(sentence, `"${m[1]}" in: ${sentence}`).toMatch(/\b(no|not|yet|upstream)\b/i);
        }
      });

      it("uses 'mission control' only to name the scene on /agent-worlds/", () => {
        if (/\bmission control\b/i.test(text)) expect(page.name).toBe("agent-worlds/index.html");
      });

      it("says 'hosted service' only in the 'no hosted service' line or the Hosted waitlist card", () => {
        for (const m of text.matchAll(/\bhosted service\b/gi)) {
          const before = text.slice(Math.max(0, (m.index ?? 0) - 12), m.index ?? 0);
          expect(before, `hosted service at …${before}…`).toMatch(/\bno\s+$/i);
        }
      });

      it("keeps [post] copy behind nightsVerified", () => {
        if (site.nightsVerified) return;
        expect(text).not.toMatch(/\bkeeps going after you leave\b/i);
        expect(text).not.toMatch(/\bVerified overnight on\b/i);
        expect(text).not.toMatch(/\bRecorded on Claude Code\b/i);
        expect(text).not.toMatch(/\bMorning report:\s*\d/i);
      });

      it("labels unshipped commands and grants as in development", () => {
        if (!site.shipped.dawnGrants) {
          for (const m of text.matchAll(/Allow until 07:00/g)) expect(text.slice(m.index ?? 0, (m.index ?? 0) + 60)).toMatch(/in development/i);
        }
        // The chain check ships as `security verify`; `audit verify` was never a command.
        expect(text).not.toMatch(/warding audit verify/);
        if (!site.shipped.charterCommand) {
          for (const m of text.matchAll(/warding charter\b/g)) expect(text.slice(m.index ?? 0, (m.index ?? 0) + 80)).toMatch(/coming|in development/i);
        }
        if (!site.shipped.morningReport) expect(text).not.toMatch(/\bMorning report:\s*\d/i);
      });
    });
  }
});
