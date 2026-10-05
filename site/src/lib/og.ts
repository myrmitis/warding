import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";
import { site, siteHost } from "../data/site";
import { createOffice, applySources, update, draw, W, H } from "../islands/world/office";
import { SvgRecorder } from "../islands/world/svgRecorder";
import { BEATS } from "../islands/world/timeline";

/**
 * Build-time OG cards (brand-book §14): Paper for feature, compare, guide and
 * pricing pages; Night for the homepage, Agent Worlds, /verified and night
 * posts. Fonts are the static .woff files (satori reads no WOFF2 and no
 * variable fonts). The Night card carries a real frame of the Office world
 * drawn by the same renderer through an SVG recorder, at the build hour.
 */
const require = createRequire(import.meta.url);
const fontFile = (pkg: string, file: string) => readFile(require.resolve(`${pkg}/files/${file}`));
// Resolved from the project root: the prerender runs from a bundled chunk under
// dist/.prerender, so a URL relative to import.meta.url would point nowhere.
const departureWoff = resolve(process.cwd(), "src/assets/fonts/DepartureMono-Regular.woff");

type Font = { name: string; data: Buffer; weight: 400 | 600; style: "normal" };
let fonts: Promise<Font[]> | undefined;
function loadFonts() {
  fonts ??= Promise.all([
    fontFile("@fontsource/fraunces", "fraunces-latin-600-normal.woff").then((data) => ({ name: "Fraunces", data, weight: 600 as const, style: "normal" as const })),
    fontFile("@fontsource/ibm-plex-sans", "ibm-plex-sans-latin-400-normal.woff").then((data) => ({ name: "IBM Plex Sans", data, weight: 400 as const, style: "normal" as const })),
    fontFile("@fontsource/ibm-plex-mono", "ibm-plex-mono-latin-400-normal.woff").then((data) => ({ name: "IBM Plex Mono", data, weight: 400 as const, style: "normal" as const })),
    readFile(departureWoff).then((data) => ({ name: "Departure Mono", data, weight: 400 as const, style: "normal" as const })),
  ]);
  return fonts;
}

const PAPER = { bg: "#F3EEE3", ink: "#1A1814", ink2: "#5E584D", line: "#D9D0BF", seal: "#B3301A", foil: "#C98A00" };
const NIGHT = { bg: "#0B0E14", fg: "#ECE8E1", fg2: "#9AA3B5", line: "#2A3244", lamp: "#FFB547" };

// Plain object trees instead of JSX so this stays a .ts module.
const el = (type: string, style: Record<string, unknown>, children?: unknown) => ({ type, props: { style, children } });

function sealSvg(ink: string, seal: string, bg: string, size: number) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="${size}" height="${size}"><circle cx="32" cy="32" r="28" fill="none" stroke="${ink}" stroke-width="2.5"/><circle cx="32" cy="32" r="24" fill="none" stroke="${ink}" stroke-width="0.75"/><circle cx="32" cy="25" r="6" fill="${ink}"/><rect x="29" y="28" width="6" height="18" fill="${ink}"/><rect x="25" y="33" width="14" height="2.5" fill="${seal}"/><rect x="25" y="37.5" width="14" height="2.5" fill="${seal}"/><rect x="25" y="42" width="14" height="2.5" fill="${seal}"/><rect x="29" y="33" width="6" height="2.5" fill="${bg}"/><rect x="29" y="37.5" width="6" height="2.5" fill="${bg}"/><rect x="29" y="42" width="6" height="2.5" fill="${bg}"/><rect x="44" y="18" width="3" height="3" fill="${seal}"/></svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

function bars(color: string) {
  return el("div", { display: "flex", gap: 4.5 }, [0, 1, 2].map(() => el("div", { width: 14, height: 2.5, background: color })));
}

function titleSize(h1: string) {
  return h1.length > 44 ? 56 : 72;
}

export interface OgSpec { h1: string; qualifier: string; register: "paper" | "night" }

/** A frame of the Office world as an SVG group, drawn by the shipping renderer. */
function officeFrameSvg(scale: number): string {
  const state = createOffice(11);
  const beat = BEATS[0];
  applySources(state, beat.sources, { instant: true, tick: 0 });
  for (let t = 1; t < 40; t++) update(state, t);
  const rec = new SvgRecorder();
  const now = new Date();
  draw(state, rec, { S: scale, textScale: 1, hour: now.getHours(), minute: now.getMinutes(), noText: true }, 40);
  return rec.toSvgGroup();
}

export async function renderOg(spec: OgSpec): Promise<Uint8Array> {
  const fontList = await loadFonts();
  const paper = spec.register === "paper";
  const size = titleSize(spec.h1);
  const tree = paper
    ? el("div", { width: "100%", height: "100%", display: "flex", flexDirection: "column", background: PAPER.bg, color: PAPER.ink, fontFamily: "IBM Plex Sans", position: "relative" }, [
        el("div", { position: "absolute", left: 48, top: 48, right: 48, bottom: 48, border: `1px solid ${PAPER.foil}` }),
        el("div", { display: "flex", alignItems: "center", gap: 16, position: "absolute", left: 96, top: 88 }, [
          { type: "img", props: { src: sealSvg(PAPER.ink, PAPER.seal, PAPER.bg, 72), width: 72, height: 72 } },
          el("div", { fontFamily: "Fraunces", fontSize: 40, fontWeight: 600, letterSpacing: -0.6 }, "warding"),
        ]),
        el("div", { position: "absolute", left: 96, top: 220, width: 900, fontFamily: "Fraunces", fontSize: size, fontWeight: 600, lineHeight: 1.05, letterSpacing: -1 }, spec.h1),
        el("div", { position: "absolute", left: 96, top: 540, fontSize: 26, color: PAPER.ink2 }, spec.qualifier),
        el("div", { position: "absolute", right: 96, top: 548, display: "flex", alignItems: "center", gap: 16 }, [
          bars(PAPER.seal),
          el("div", { fontFamily: "IBM Plex Mono", fontSize: 22, color: PAPER.ink2 }, siteHost),
        ]),
      ])
    : el("div", { width: "100%", height: "100%", display: "flex", background: NIGHT.bg, color: NIGHT.fg, fontFamily: "IBM Plex Sans", position: "relative" }, [
        el("div", { display: "flex", alignItems: "center", gap: 16, position: "absolute", left: 72, top: 72 }, [
          { type: "img", props: { src: sealSvg(NIGHT.fg, NIGHT.fg, NIGHT.bg, 56), width: 56, height: 56 } },
          el("div", { fontFamily: "Fraunces", fontSize: 40, fontWeight: 600, letterSpacing: -0.6 }, "warding"),
        ]),
        el("div", { position: "absolute", left: 72, top: 180, width: 520, fontFamily: "Fraunces", fontSize: spec.h1.length > 30 ? 56 : 68, fontWeight: 600, lineHeight: 1.05, letterSpacing: -1 }, spec.h1),
        el("div", { position: "absolute", left: 72, top: 440, width: 520, fontSize: 24, lineHeight: 1.3, color: NIGHT.fg2 }, spec.qualifier),
        el("div", { position: "absolute", left: 72, top: 540, display: "flex", alignItems: "center", gap: 18 }, [
          el("div", { fontFamily: "Departure Mono", fontSize: 44, color: NIGHT.lamp }, "02:14"),
          el("div", { display: "flex", flexWrap: "wrap", width: 32, height: 32, border: `2px solid ${NIGHT.fg2}` }, [
            el("div", { width: 14, height: 14, borderRight: `2px solid ${NIGHT.fg2}`, borderBottom: `2px solid ${NIGHT.fg2}` }),
            el("div", { width: 14, height: 14, borderBottom: `2px solid ${NIGHT.fg2}` }),
            el("div", { width: 14, height: 14, borderRight: `2px solid ${NIGHT.fg2}` }),
            el("div", { width: 14, height: 14, background: NIGHT.lamp }),
          ]),
        ]),
        el("div", { position: "absolute", right: 24, bottom: 20, fontFamily: "IBM Plex Mono", fontSize: 22, color: NIGHT.fg2 }, siteHost),
        // The world frame: 560 px wide at 2x, cropped to the right column.
        el("div", { position: "absolute", left: 640, top: 35, width: 560, height: 560, border: `1px solid ${NIGHT.line}` }),
      ]);
  const svg = await satori(tree as never, { width: 1200, height: 630, fonts: fontList });
  let out = svg;
  if (!paper) {
    // Inject the recorded office frame (2x, cropped) before the closing tag.
    const group = officeFrameSvg(2);
    const clip = `<clipPath id="worldclip"><rect x="641" y="36" width="558" height="558"/></clipPath>`;
    const g = `<g clip-path="url(#worldclip)"><g transform="translate(${641 - (W * 2 - 558) / 2}, ${36 - (H * 2 - 558) / 2})">${group}</g></g>`;
    out = svg.replace(/<\/svg>\s*$/, `${clip}${g}</svg>`);
  }
  return new Resvg(out, { fitTo: { mode: "width", value: 1200 } }).render().asPng();
}

export const defaultQualifier = `${site.name} · your agent, your box`;
