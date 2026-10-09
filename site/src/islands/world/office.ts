/**
 * The Office world renderer, ported from the product's shipping scene
 * (website/src/pages/scenes/OfficeScene.tsx) as a pure module: state in, pixels
 * out. No React, no DOM, no dashboard dependencies, so the same code draws the
 * live hero, the margin drolleries and the build-time OG frame.
 *
 * Changes from the product copy, all called for by brand-book §12:
 *   - palette remapped to the Night tokens; the window sky follows the local hour
 *   - the leftover chat lines are agent lines
 *   - the emoji kind badges are pixel glyphs (no emoji anywhere)
 *   - time-based ticks at 30 per second (the product ticks once per frame)
 *   - a `refused` state (sprite frozen in the seal colour) and the pending-approval
 *     overlay; the hand-raised pose is not drawn because it has not shipped
 *   - agents leave through the door instead of vanishing
 */
import type { AgentSource, Ctx } from "./types";

export const W = 440;
export const H = 300;
export const TICKS_PER_SECOND = 30;

const DOOR = { x: 0, y: 100, w: 12, h: 50 };
const MAX_DESKS = 6;
/** Seat arrivals apart (front-left, front-right, back-centre first) so labels do not collide. */
const DESK_SEATING = [0, 2, 4, 1, 5, 3];
const DESK_POSITIONS = [
  { x: 50, y: 120 }, { x: 150, y: 120 }, { x: 250, y: 120 },
  { x: 50, y: 200 }, { x: 150, y: 200 }, { x: 250, y: 200 },
];
/** Brand sprite colours. The seal (#FF7A5C) is reserved for the refused state. */
export const AGENT_COLORS = ["#FFB547", "#5EE6A0", "#8EA8FF", "#F5C542", "#ECE8E1", "#9AA3B5", "#C98A00"];
const SEAL = "#FF7A5C";
const HELD = "#F5C542";
const GRANTED = "#5EE6A0";
const LAMP = "#FFB547";
const INK = "#0B0E14";
const DESK_ACCENTS = AGENT_COLORS;
const HAIR = ["#1A1814", "#5c3a1e", "#C98A00", "#2A3244", "#6e4b2a"];

type DeskItemKind = "mug" | "photo" | "plant" | "notebook" | "headphones";
interface DeskItem { kind: DeskItemKind; ox: number; oy: number }
const DESK_ITEM_SETS: DeskItem[][] = [
  [{ kind: "mug", ox: 2, oy: 12 }, { kind: "photo", ox: 22, oy: 6 }],
  [{ kind: "plant", ox: 1, oy: 8 }, { kind: "notebook", ox: 20, oy: 13 }],
  [{ kind: "headphones", ox: 23, oy: 10 }, { kind: "mug", ox: 1, oy: 13 }],
  [{ kind: "photo", ox: 1, oy: 6 }, { kind: "plant", ox: 24, oy: 8 }],
  [{ kind: "notebook", ox: 2, oy: 13 }, { kind: "headphones", ox: 22, oy: 10 }],
  [{ kind: "mug", ox: 23, oy: 12 }, { kind: "photo", ox: 1, oy: 6 }],
  [{ kind: "plant", ox: 24, oy: 8 }, { kind: "notebook", ox: 2, oy: 13 }],
  [{ kind: "headphones", ox: 1, oy: 10 }, { kind: "mug", ox: 23, oy: 12 }],
];

const COL = {
  floor: "#352a1f", floorAlt: "#3d3125", wall: "#121722", wallTrim: "#2A3244",
  desk: "#5c4033", deskTop: "#7a5c47", monitor: "#1C2333", screen: "#0f1f16",
  screenText: GRANTED, screenOff: "#141A26",
  cubicleWall: "#2A3244", cubicleTop: "#3a4358",
  plant: "#2E6B45", plantPot: "#8b4513", plantLight: "#4fbf80",
  chair: "#1C2333", coffee: "#6b4226", coffeeMug: "#ECE8E1",
  whiteboard: "#ECE8E1", whiteboardFrame: "#9AA3B5",
  lightFixture: "#3a4358", rug: "#2b1f2e", rugPattern: "#3a2a3e",
  windowFrame: "#9AA3B5", star: "#ECE8E1",
  door: "#6b4226", doorFrame: "#4a3520", doorKnob: LAMP,
  mug: "#C98A00", photo: HELD, notebook: "#8EA8FF", headphones: "#7D869A",
  skin: "#f2d3b8",
};
/** Agent lines, shown when two sprites meet (brand-book §12). */
const CHAT_LINES: [string, string][] = [
  ["opening PR #412", "running tests"],
  ["asked for approval", "waiting on you"],
  ["refused: ~/.aws", "logged · chained"],
  ["nightly-deps · done", "posting report"],
];
const COFFEE_MACHINE = { x: 390, y: 240 };
const WHITEBOARD = { x: 350, y: 14, w: 60, h: 36 };
const CLOCK_POS = { x: 130, y: 22 };
/** The wall sign sits between the clock and the shelves, clear of both. */
const SIGN_X = 184;
/** Centre of the rug, where two agents meet to talk. */
const MEET = { x: 165, y: 170 };
const WINDOW_POS = { x: 60, y: 10, w: 50, h: 40 };
const PLANTS = [
  { x: 15, y: 98 }, { x: 95, y: 98 }, { x: 175, y: 98 }, { x: 255, y: 98 },
  { x: 335, y: 98 }, { x: 15, y: 260 }, { x: 200, y: 260 }, { x: 420, y: 260 },
];
const SPEECH_TICKS = 7 * TICKS_PER_SECOND;

type Activity = "entering" | "desk" | "collab" | "coffee" | "whiteboard" | "leaving";
export interface OfficeAgent {
  id: string; name: string; label: string; kind: AgentSource["kind"];
  x: number; y: number; tx: number; ty: number;
  deskIdx: number; color: string; detail: string;
  dir: number; activity: Activity; running: boolean; actTimer: number;
  lastMessage: string; msgAt: number;
  pending: string; refused: string; waiting: boolean;
}
interface Desk { x: number; y: number; occupied: boolean; accent: string; items: DeskItem[] }
interface Particle { x: number; y: number; vx: number; vy: number; life: number; maxLife: number }

export interface OfficeState {
  agents: OfficeAgent[];
  desks: Desk[];
  collab: [OfficeAgent, OfficeAgent] | null;
  speech: { a: string; b: string };
  particles: Particle[];
  kanban: string[];
  rand: () => number;
}

/** Deterministic PRNG so a build-time frame is reproducible. */
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createOffice(seed = 7): OfficeState {
  return {
    agents: [],
    desks: DESK_POSITIONS.map((pos, i) => ({
      x: pos.x, y: pos.y, occupied: false,
      accent: DESK_ACCENTS[i % DESK_ACCENTS.length], items: DESK_ITEM_SETS[i % DESK_ITEM_SETS.length],
    })),
    collab: null,
    speech: { a: "", b: "" },
    particles: [],
    kanban: [],
    rand: mulberry32(seed),
  };
}

export interface ApplyOptions {
  /** Place new agents at their desks instead of walking them in from the door. */
  instant?: boolean;
  /** Agents already present that should walk back in from the door. */
  reenter?: string[];
  tick?: number;
}

/** Reconcile sources with the office: keep, add, or walk departed agents out. */
export function applySources(state: OfficeState, sources: AgentSource[], opts: ApplyOptions = {}) {
  const capped = sources.slice(0, MAX_DESKS);
  const tick = opts.tick ?? 0;
  const existing = state.agents;
  const desks = state.desks;
  desks.forEach((d) => (d.occupied = false));
  existing.forEach((a) => { if (a.activity !== "leaving" && a.deskIdx >= 0) desks[a.deskIdx].occupied = true; });
  const next: OfficeAgent[] = [];

  capped.forEach((src) => {
    const prev = existing.find((a) => a.id === src.id && a.activity !== "leaving");
    if (prev) {
      prev.name = src.name; prev.detail = src.detail; prev.running = src.running;
      const msg = src.lastMessage || "";
      if (msg !== prev.lastMessage) { prev.lastMessage = msg; prev.msgAt = tick; }
      prev.pending = src.pendingApproval?.tool || "";
      prev.refused = src.refused || "";
      prev.waiting = !!src.waitingForInput;
      if (opts.reenter?.includes(src.id)) {
        prev.x = DOOR.x + 6; prev.y = DOOR.y + 25; prev.activity = "entering"; prev.actTimer = 0;
        const dk = desks[prev.deskIdx]; prev.tx = dk.x + 10; prev.ty = dk.y + 20;
      }
      next.push(prev);
      return;
    }
    // Seat new arrivals apart so their labels do not collide.
    const deskIdx = DESK_SEATING.find((i) => !desks[i].occupied) ?? -1;
    if (deskIdx < 0) return;
    desks[deskIdx].occupied = true;
    const dk = desks[deskIdx];
    const instant = !!opts.instant;
    next.push({
      id: src.id, name: src.name, label: src.label, kind: src.kind,
      x: instant ? dk.x + 10 : DOOR.x + 6, y: instant ? dk.y + 20 : DOOR.y + 25,
      tx: dk.x + 10, ty: dk.y + 20,
      deskIdx, color: AGENT_COLORS[deskIdx % AGENT_COLORS.length],
      detail: src.detail, dir: 1, activity: instant ? "desk" : "entering",
      running: src.running, actTimer: 0,
      lastMessage: src.lastMessage || "", msgAt: src.lastMessage ? tick : -SPEECH_TICKS,
      pending: src.pendingApproval?.tool || "", refused: src.refused || "", waiting: !!src.waitingForInput,
    });
  });

  // Departed agents walk to the door, then vanish (see update()).
  existing.forEach((a) => {
    if (next.includes(a)) return;
    if (a.activity === "leaving") { next.push(a); return; }
    if (opts.instant) return;
    if (a.deskIdx >= 0) desks[a.deskIdx].occupied = false;
    a.activity = "leaving"; a.tx = DOOR.x + 6; a.ty = DOOR.y + 25; a.pending = ""; a.refused = "";
    if (state.collab?.includes(a)) { state.collab = null; state.speech = { a: "", b: "" }; }
    next.push(a);
  });

  state.kanban = capped.filter((s) => s.running).map((s) => s.name).slice(0, 4);
  if (state.kanban.length === 0) state.kanban = ["no tasks"];
  state.agents = next;
}

/* ── Update ── */
export function update(state: OfficeState, t: number) {
  const { agents, desks, rand } = state;

  if (t % 3 === 0 && state.particles.length < 15) {
    state.particles.push({
      x: rand() * W, y: 85 + rand() * (H - 90),
      vx: (rand() - 0.5) * 0.16, vy: -0.08 - rand() * 0.08,
      life: 0, maxLife: 125 + rand() * 150,
    });
  }
  state.particles.forEach((p) => { p.x += p.vx; p.y += p.vy; p.vx += (rand() - 0.5) * 0.03; p.life++; });
  state.particles = state.particles.filter((p) => p.life < p.maxLife && p.y > 70);

  agents.forEach((a) => {
    if (a.refused) return; // frozen at the gate
    const ddx = a.tx - a.x, ddy = a.ty - a.y;
    const dist = Math.sqrt(ddx * ddx + ddy * ddy);
    if (dist > 1.5) {
      a.x += (ddx / dist) * 1.3; a.y += (ddy / dist) * 1.3;
      a.dir = ddx > 0 ? 1 : -1;
      return;
    }
    a.x = a.tx; a.y = a.ty;
    if (a.activity === "entering") a.activity = "desk";
    if (a.activity === "collab" || a.activity === "coffee" || a.activity === "whiteboard") {
      a.actTimer++;
      const limit = a.activity === "collab" ? 300 : 200;
      if (a.actTimer > limit) {
        const dk = desks[a.deskIdx];
        a.tx = dk.x + 10; a.ty = dk.y + 20; a.activity = "desk"; a.actTimer = 0;
        if (state.collab?.includes(a)) {
          state.collab.forEach((c) => {
            const ck = desks[c.deskIdx];
            c.tx = ck.x + 10; c.ty = ck.y + 20; c.activity = "desk"; c.actTimer = 0;
          });
          state.collab = null; state.speech = { a: "", b: "" };
        }
      }
    }
  });
  state.agents = agents.filter((a) => !(a.activity === "leaving" && Math.abs(a.x - a.tx) < 2 && Math.abs(a.y - a.ty) < 2));

  if (state.collab) {
    const [ca, cb] = state.collab;
    const arrived = Math.abs(ca.x - ca.tx) < 2 && Math.abs(ca.y - ca.ty) < 2 && Math.abs(cb.x - cb.tx) < 2 && Math.abs(cb.y - cb.ty) < 2;
    if (arrived && Math.min(ca.actTimer, cb.actTimer) === 30) {
      const lines = CHAT_LINES[(rand() * CHAT_LINES.length) | 0];
      state.speech = { a: lines[0], b: lines[1] };
    }
  }

  const deskAgents = state.agents.filter((a) => a.activity === "desk" && !a.pending && !a.refused);
  if (t % 900 === 0 && !state.collab && deskAgents.length >= 2 && rand() < 0.35) {
    const i = (rand() * deskAgents.length) | 0;
    const j = (i + 1 + ((rand() * (deskAgents.length - 1)) | 0)) % deskAgents.length;
    const a = deskAgents[i], b = deskAgents[j];
    a.tx = MEET.x - 10; a.ty = MEET.y; b.tx = MEET.x + 10; b.ty = MEET.y;
    a.activity = "collab"; b.activity = "collab"; a.actTimer = 0; b.actTimer = 0;
    state.collab = [a, b]; state.speech = { a: "", b: "" };
  }
  if (t % 1200 === 300 && !state.collab && deskAgents.length > 0 && rand() < 0.3) {
    const a = deskAgents[(rand() * deskAgents.length) | 0];
    a.activity = "coffee"; a.actTimer = 0; a.tx = COFFEE_MACHINE.x - 15; a.ty = COFFEE_MACHINE.y + 2;
  }
  if (t % 1500 === 450 && !state.collab && deskAgents.length > 0 && rand() < 0.25) {
    const a = deskAgents[(rand() * deskAgents.length) | 0];
    a.activity = "whiteboard"; a.actTimer = 0; a.tx = WHITEBOARD.x + 20; a.ty = WHITEBOARD.y + 50;
  }
}

/* ── Drawing helpers ── */
export interface DrawEnv {
  /** Canvas pixels per logical unit. */
  S: number;
  /** Device pixels per CSS pixel, so labels stay 11 CSS px whatever the scale. */
  textScale: number;
  hour: number;
  minute: number;
  /** Skip text: the build-time recorder has no font metrics. */
  noText?: boolean;
  /** Draw the "n/6 desks" counter in the corner (the live hero shows it in the DOM instead). */
  counter?: boolean;
}

const dp = (X: Ctx, S: number) => (x: number, y: number, w: number, h: number, c: string) => {
  X.fillStyle = c; X.fillRect(x * S, y * S, w * S, h * S);
};

function mix(a: string, b: string, k: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const m = pa.map((v, i) => Math.round(v + (pb[i] - v) * k));
  return `#${m.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
const smooth = (a: number, b: number, x: number) => { const k = Math.min(1, Math.max(0, (x - a) / (b - a))); return k * k * (3 - 2 * k); };
/** Daylight 0..1 from the local hour: night before ~6, day by ~8, dusk 17:30–20:30. */
export function daylight(hour: number, minute = 0): number {
  const h = hour + minute / 60;
  return smooth(5.5, 8, h) * (1 - smooth(17.5, 20.5, h));
}
export function skyColor(hour: number, minute = 0): string {
  return mix("#2A4A6A", "#7FA7D9", daylight(hour, minute));
}

const font = (env: DrawEnv, px: number) => `${px * env.textScale}px "Departure Mono", "IBM Plex Mono", ui-monospace, monospace`;

function label(X: Ctx, env: DrawEnv, text: string, x: number, y: number, opts: { color: string; bg?: string; align?: CanvasTextAlign; px?: number; pad?: number }) {
  if (env.noText) return;
  const S = env.S;
  const px = opts.px ?? 11;
  X.font = font(env, px);
  X.textAlign = opts.align ?? "start";
  X.textBaseline = "middle";
  if (opts.bg) {
    const tw = X.measureText(text).width;
    const pad = (opts.pad ?? 3) * env.textScale;
    const bh = px * env.textScale + pad * 1.4;
    let bx = x * S;
    if (X.textAlign === "center") bx -= tw / 2; else if (X.textAlign === "end") bx -= tw;
    X.fillStyle = opts.bg; X.fillRect(bx - pad, y * S - bh / 2, tw + pad * 2, bh);
  }
  X.fillStyle = opts.color; X.fillText(text, x * S, y * S);
  X.textAlign = "start"; X.textBaseline = "alphabetic";
}

/** One sprite. Shared by the office and the margin drolleries. */
export interface SpriteOpts {
  color: string; t: number; moving?: boolean; dir?: number; typing?: boolean;
  asleep?: boolean; carry?: "envelope" | "cup" | ""; frozen?: boolean; hairIdx?: number;
  /** Paper plates use the three-ink risograph set; override the skin and ink there. */
  skin?: string; ink?: string;
}
export function drawSprite(X: Ctx, S: number, bx: number, by: number, o: SpriteOpts) {
  const d = dp(X, S);
  const t = o.t;
  const mv = !!o.moving && !o.frozen;
  const bob = mv ? (Math.sin(t * 0.24 + bx) | 0) : 0;
  const dir = o.dir ?? 1;
  const ink = o.ink ?? INK;
  X.fillStyle = "rgba(0,0,0,0.18)"; X.fillRect((bx + 1) * S, (by + 10) * S, 6 * S, 2 * S);
  d(bx, by + bob, 8, 8, o.color);
  d(bx + 1, by - 6 + bob, 6, 6, o.skin ?? COL.skin);
  const hair = o.ink ?? HAIR[(o.hairIdx ?? 0) % HAIR.length];
  d(bx, by - 6 + bob, 1, 4, hair); d(bx + 7, by - 6 + bob, 1, 4, hair); d(bx + 1, by - 7 + bob, 6, 1, hair);
  const ex = dir > 0 ? 2 : 1;
  const blink = o.asleep || (!o.frozen && t % 120 < 3);
  if (!blink) { d(bx + ex + 1, by - 4 + bob, 1, 1, ink); d(bx + ex + 3, by - 4 + bob, 1, 1, ink); }
  else { d(bx + ex + 1, by - 3 + bob, 1, 0.5, ink); d(bx + ex + 3, by - 3 + bob, 1, 0.5, ink); }
  if (o.typing && !o.frozen) d(bx + ex + 1.5, by - 2 + bob, 2, 0.5, "#c88");
  const st = (t >> 2) & 1;
  if (mv) { d(bx + 1 + (st ? 2 : 0), by + 8 + bob, 2, 3, o.color); d(bx + 5 - (st ? 2 : 0), by + 8 + bob, 2, 3, o.color); }
  else { d(bx + 1, by + 8, 2, 3, o.color); d(bx + 5, by + 8, 2, 3, o.color); }
  if (o.typing && !mv && !o.frozen) {
    const arm = (t >> 1) & 1;
    d(bx - 1, by + 2 + bob + arm, 1, 3, o.color); d(bx + 8, by + 2 + bob + (1 - arm), 1, 3, o.color);
  }
  if (o.carry === "cup") d(bx + (dir > 0 ? 9 : -3), by + 3 + bob, 2, 3, COL.coffeeMug);
  if (o.carry === "envelope") { d(bx + (dir > 0 ? 8 : -4), by + 2 + bob, 4, 3, "#ECE8E1"); d(bx + (dir > 0 ? 9 : -3), by + 3 + bob, 2, 1, SEAL); }
  if (o.asleep) {
    const z = (t >> 4) % 3;
    for (let i = 0; i <= z; i++) d(bx + 9 + i * 2, by - 8 - i * 3, 1, 1, "#9AA3B5");
  }
}

function kindGlyph(X: Ctx, S: number, kind: AgentSource["kind"], x: number, y: number) {
  const d = dp(X, S);
  const c = "#9AA3B5";
  if (kind === "cron") { d(x, y, 4, 1, c); d(x, y + 3, 4, 1, c); d(x, y + 1, 1, 2, c); d(x + 3, y + 1, 1, 2, c); d(x + 1.5, y + 1.5, 1, 1, LAMP); }
  else if (kind === "spawn") { d(x, y, 1, 4, c); d(x + 3, y, 1, 2, c); d(x + 1, y + 1.5, 2, 1, c); }
  else { d(x, y, 4, 3, c); d(x + 1, y + 3, 1, 1, c); }
}

/* ── Main draw ── */
export function draw(state: OfficeState, X: Ctx, env: DrawEnv, t: number) {
  const { S } = env;
  const d = dp(X, S);
  const { agents, desks } = state;

  // Background
  d(0, 0, W, H, COL.wall);
  for (let i = 0; i < W; i += 16) for (let j = 80; j < H; j += 16) d(i, j, 16, 16, ((i / 16 + j / 16) & 1) ? COL.floorAlt : COL.floor);
  d(0, 78, W, 3, COL.wallTrim);

  // Window: sky by local hour, stars at night, a moon or sun
  {
    const { x, y, w, h } = WINDOW_POS;
    const day = daylight(env.hour, env.minute);
    d(x - 1, y - 1, w + 2, h + 2, COL.windowFrame);
    d(x, y, w, h, skyColor(env.hour, env.minute));
    if (day < 0.35) for (let i = 0; i < 6; i++) {
      const sx = x + 3 + ((i * 11 + t * 0.016) % (w - 6));
      const sy = y + 2 + ((i * 7) % (h - 8));
      if (Math.sin(t * 0.08 + i * 2.5) > 0.3) d(sx, sy, 1, 1, COL.star);
    }
    d(x + w - 12, y + 5, 6, 6, day > 0.5 ? "#FFE9A8" : "#dde");
    if (day <= 0.5) d(x + w - 11, y + 4, 4, 4, skyColor(env.hour, env.minute));
    d(x + w / 2, y, 1, h, COL.windowFrame); d(x, y + h / 2, w, 1, COL.windowFrame);
    X.fillStyle = "rgba(100,150,200,0.03)"; X.fillRect((x + 5) * S, 82 * S, (w - 10) * S, 25 * S);
  }

  // Sign
  label(X, env, "warding", SIGN_X, 30, { color: LAMP, align: "center", px: 16 });
  d(SIGN_X - 28, 36, 56, 1, LAMP);
  label(X, env, "the late desk", SIGN_X, 43, { color: "#C98A00", align: "center", px: 8 });

  // Bookshelves
  {
    const bc = ["#FFB547", "#8EA8FF", "#5EE6A0", "#F5C542", "#C98A00", "#9AA3B5", "#ECE8E1"];
    [{ sx: 230, sy: 50 }, { sx: 290, sy: 50 }].forEach(({ sx, sy }, si) => {
      d(sx, sy, 28, 2, COL.desk); d(sx, sy - 16, 28, 2, COL.desk);
      let bxp = sx + 1;
      for (let b = 0; b < 4; b++) { const bh = 7 + ((b * 3) % 5); d(bxp, sy - bh, 5, bh, bc[(b + si * 3) % bc.length]); bxp += 6; }
      bxp = sx + 1;
      for (let b = 0; b < 3; b++) { const bh = 5 + ((b * 4) % 4); d(bxp, sy - 16 - bh, 6, bh, bc[(b + si * 2 + 2) % bc.length]); bxp += 8; }
    });
  }

  // Whiteboard
  {
    const { x, y, w, h } = WHITEBOARD;
    d(x - 1, y - 1, w + 2, h + 2, COL.whiteboardFrame); d(x, y, w, h, COL.whiteboard);
    const cw = w / 3;
    ["todo", "active", "done"].forEach((c, i) => {
      if (i > 0) d(x + cw * i, y, 0.5, h, "#bbb");
      label(X, env, c, x + cw * i + 1, y + 4, { color: "#6F685B", px: 6 });
    });
    const colors = ["#F5C542", "#FF7A5C", "#8EA8FF", "#5EE6A0"];
    state.kanban.forEach((task, i) => {
      const col = Math.min(i, 2), row = i < 1 ? 0 : i < 3 ? i - 1 : 0;
      const nx = x + cw * col + 1, ny = y + 7 + row * 9;
      d(nx, ny, cw - 2, 7, colors[i % colors.length]);
      label(X, env, task.slice(0, 7), nx + 1, ny + 3.5, { color: INK, px: 6 });
    });
  }

  // Wall clock: the visitor's local time
  {
    const { x, y } = CLOCK_POS;
    d(x - 8, y - 8, 16, 16, "#3a4358"); d(x - 7, y - 7, 14, 14, "#141A26");
    for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; d(x + Math.cos(a) * 5, y + Math.sin(a) * 5, 1, 1, "#7D869A"); }
    const ha = ((env.hour % 12) / 12 + env.minute / 720) * Math.PI * 2 - Math.PI / 2;
    const ma = (env.minute / 60) * Math.PI * 2 - Math.PI / 2;
    X.strokeStyle = LAMP; X.lineWidth = S; X.beginPath(); X.moveTo(x * S, y * S); X.lineTo((x + Math.cos(ha) * 3.5) * S, (y + Math.sin(ha) * 3.5) * S); X.stroke();
    X.strokeStyle = "#ECE8E1"; X.lineWidth = S; X.beginPath(); X.moveTo(x * S, y * S); X.lineTo((x + Math.cos(ma) * 5) * S, (y + Math.sin(ma) * 5) * S); X.stroke();
    if ((t >> 3) & 1) d(x - 0.5, y - 0.5, 1, 1, SEAL);
  }

  // Door
  {
    const { x, y, w, h } = DOOR;
    d(x, y, w, h, COL.doorFrame); d(x + 1, y + 1, w - 2, h - 2, COL.door); d(x + w - 3, y + h / 2, 1.5, 1.5, COL.doorKnob);
    label(X, env, "in", x + 2, y - 4, { color: "#7D869A", px: 7 });
    if (agents.some((a) => a.activity === "entering" || a.activity === "leaving") && ((t >> 2) & 1)) {
      X.fillStyle = "rgba(255,181,71,0.10)"; X.fillRect(x * S, y * S, w * S, h * S);
    }
  }

  // Ceiling lamps: sodium amber, flicker amplitude 0.12
  [70, 170, 270, 370].forEach((lx, i) => {
    d(lx - 4, 80, 8, 2, COL.lightFixture); d(lx - 2, 78, 4, 2, COL.lightFixture);
    const flicker = 1 + Math.sin(t * 0.05 + i * 1.3) * 0.12;
    const g = X.createRadialGradient(lx * S, 82 * S, 0, lx * S, 82 * S, 45 * S * flicker);
    g.addColorStop(0, "rgba(255,181,71,0.09)"); g.addColorStop(1, "rgba(255,181,71,0)");
    X.fillStyle = g; X.fillRect((lx - 45) * S, 80 * S, 90 * S, 50 * S);
  });

  // Rug
  [[40, 14, COL.rug], [34, 10, COL.rugPattern], [28, 7, COL.rug]].forEach(([rx, ry, c]) => {
    X.fillStyle = c as string; X.beginPath(); X.ellipse(MEET.x * S, (MEET.y + 5) * S, (rx as number) * S, (ry as number) * S, 0, 0, Math.PI * 2); X.fill();
  });

  // Desks
  desks.forEach((desk) => {
    const { x: dx, y: dy, accent, items, occupied } = desk;
    // Unused desks recede instead of carrying an "empty" label.
    X.save(); X.globalAlpha = occupied ? 1 : 0.45;
    d(dx - 2, dy - 2, 1, 32, COL.cubicleWall); d(dx - 2, dy - 2, 34, 1, COL.cubicleWall); d(dx + 31, dy - 2, 1, 32, COL.cubicleWall);
    d(dx - 2, dy - 3, 35, 1, COL.cubicleTop);
    d(dx, dy + 16, 28, 3, COL.deskTop); d(dx, dy + 15, 28, 1, accent); d(dx + 1, dy + 14, 26, 1, COL.desk);
    d(dx + 2, dy + 19, 2, 10, COL.desk); d(dx + 24, dy + 19, 2, 10, COL.desk);
    d(dx + 9, dy + 4, 10, 10, COL.monitor); d(dx + 10, dy + 5, 8, 8, occupied ? COL.screen : COL.screenOff); d(dx + 13, dy + 14, 2, 1, COL.monitor);
    if (occupied) {
      for (let i = 0; i < 4; i++) d(dx + 11, dy + 6 + i * 1.8, 2 + ((t + i * 7) % 5), 0.8, COL.screenText);
      if ((t >> 2) & 1) d(dx + 11 + ((t >> 1) % 5), dy + 6 + ((t >> 3) % 4) * 1.8, 1, 1, COL.screenText);
      X.fillStyle = "rgba(94,230,160,0.03)"; X.fillRect((dx + 8) * S, (dy + 13) * S, 12 * S, 4 * S);
    } else if ((t >> 4) & 1) d(dx + 14, dy + 9, 1, 1, "#2A3244");
    d(dx + 10, dy + 22, 8, 3, COL.chair); d(dx + 10, dy + 25, 2, 4, COL.chair); d(dx + 16, dy + 25, 2, 4, COL.chair); d(dx + 9, dy + 19, 1, 6, COL.chair);
    items.forEach((item) => {
      const ix = dx + item.ox, iy = dy + item.oy;
      switch (item.kind) {
        case "mug": d(ix, iy, 3, 3, COL.mug); d(ix + 3, iy + 0.5, 1, 2, COL.mug);
          if (occupied && ((t >> 3) & 1)) { X.fillStyle = "rgba(255,255,255,0.1)"; X.fillRect((ix + 1) * S, (iy - 1.5) * S, S, S); } break;
        case "photo": d(ix, iy, 4, 5, "#ECE8E1"); d(ix + 0.5, iy + 0.5, 3, 3.5, accent); break;
        case "plant": d(ix + 1, iy + 3, 2, 3, COL.plantPot); d(ix, iy + 1, 4, 2, COL.plant); d(ix + 1, iy, 2, 2, COL.plantLight); break;
        case "notebook": d(ix, iy, 5, 3, COL.notebook); d(ix + 0.5, iy + 0.5, 4, 0.5, "#ECE8E1"); break;
        case "headphones": d(ix, iy, 4, 1, COL.headphones); d(ix, iy + 1, 1, 2, COL.headphones); d(ix + 3, iy + 1, 1, 2, COL.headphones); break;
      }
    });
    X.restore();
  });

  // Coffee machine
  {
    const { x, y } = COFFEE_MACHINE;
    d(x, y, 12, 16, "#3a4358"); d(x + 1, y + 1, 10, 6, "#1C2333"); d(x + 3, y + 2, 6, 4, COL.coffee);
    if ((t >> 4) & 1) d(x + 5, y + 8, 2, 1, COL.coffee);
    d(x + 3, y + 10, 6, 5, COL.coffeeMug); d(x + 2, y + 11, 1, 3, COL.coffeeMug); d(x + 4, y + 11, 4, 3, COL.coffee);
    for (let i = 0; i < 3; i++) {
      const sy = y + 8 - i * 3 - ((t * 0.08) % 3), sx = x + 4 + Math.sin(t * 0.05 + i * 2) * 1.5;
      if (sy > y - 2) { X.fillStyle = `rgba(255,255,255,${0.12 - i * 0.03})`; X.fillRect(sx * S, sy * S, 2 * S, S); }
    }
  }

  // Plants
  PLANTS.forEach(({ x: px, y: py }) => {
    d(px + 2, py + 8, 4, 6, COL.plantPot); d(px + 1, py + 8, 6, 1, COL.plantPot);
    for (let i = 0; i < 3; i++) {
      const sw = Math.sin(t * 0.024 + px + i) | 0;
      d(px + 3 + sw, py - i * 3 + 6, 2, 4, COL.plant); d(px + 1 + sw, py - i * 3 + 5, 2, 3, COL.plantLight); d(px + 5 + sw, py - i * 3 + 5, 2, 3, COL.plantLight);
    }
  });

  // Dust in the lamp light
  state.particles.forEach((p) => { X.fillStyle = `rgba(255,240,200,${Math.max(0, 0.25 * (1 - p.life / p.maxLife))})`; X.fillRect(p.x * S, p.y * S, S, S); });

  // Agents, y-sorted for depth
  [...agents].sort((a, b) => a.y - b.y).forEach((a) => {
    const bx = a.x | 0, by = a.y | 0;
    const mv = Math.abs(a.x - a.tx) > 1.5 || Math.abs(a.y - a.ty) > 1.5;
    const frozen = !!a.refused;
    drawSprite(X, S, bx, by, {
      color: frozen ? SEAL : a.color, t, moving: mv, dir: a.dir, typing: !mv && a.activity === "desk" && a.running && !a.pending,
      carry: a.activity === "coffee" ? "cup" : "", frozen, hairIdx: AGENT_COLORS.indexOf(a.color),
    });
    kindGlyph(X, S, a.kind, bx + 9, by - 6);
    const status = frozen ? "refused" : a.pending ? "waiting on you" : a.running ? "running" : "idle";
    const sc = frozen ? SEAL : a.pending ? HELD : a.running ? GRANTED : "#9AA3B5";
    label(X, env, status, bx + 4, by - 11, { color: sc, bg: "rgba(11,14,20,0.6)", align: "center", px: 7 });
    if (frozen) {
      // The stamp in-world: refused command on a seal-bordered box
      label(X, env, `REFUSED · ${a.refused}`, bx + 4, by - 20, { color: SEAL, bg: "rgba(11,14,20,0.85)", align: "center", px: 8 });
    } else if (a.pending) {
      // The existing "needs approval" overlay (no hand-raised pose yet; brand-book §12)
      label(X, env, `needs approval: ${a.pending}`, bx + 4, by - 20, { color: HELD, bg: "rgba(11,14,20,0.85)", align: "center", px: 8 });
    } else if (a.lastMessage && t - a.msgAt < SPEECH_TICKS) {
      const age = t - a.msgAt;
      const alpha = age > SPEECH_TICKS - 30 ? (SPEECH_TICKS - age) / 30 : 1;
      X.save(); X.globalAlpha = alpha;
      label(X, env, a.lastMessage, bx + 4, by - 20, { color: INK, bg: "rgba(236,232,225,0.94)", align: "center", px: 8 });
      X.restore();
    }
    label(X, env, a.name, bx + 4, by + 15, { color: "#ECE8E1", align: "center", px: 8 });
    if (a.detail) label(X, env, a.detail, bx + 4, by + 22, { color: "#9AA3B5", align: "center", px: 7 });
    // The desk tag sits where a seated agent's overlay goes; it yields to the overlay.
    const overlay = frozen || !!a.pending || (!!a.lastMessage && t - a.msgAt < SPEECH_TICKS);
    const seated = Math.abs(a.x - a.tx) < 2 && Math.abs(a.y - a.ty) < 2 && a.activity === "desk";
    if (a.deskIdx >= 0 && a.activity !== "entering" && a.activity !== "leaving" && !(overlay && seated)) {
      const dk = desks[a.deskIdx];
      label(X, env, a.name.slice(0, 8), dk.x + 15, dk.y + 1, { color: INK, bg: a.color, align: "center", px: 7 });
    }
    if (state.collab && state.collab.includes(a)) d(bx + 2, by - 16, 3, 2, LAMP);
  });

  if (state.collab) {
    const [a, b] = state.collab;
    X.strokeStyle = LAMP; X.lineWidth = S; X.setLineDash([4 * S, 4 * S]);
    X.beginPath(); X.moveTo((a.x + 4) * S, (a.y + 4) * S); X.lineTo((b.x + 4) * S, (b.y + 4) * S); X.stroke(); X.setLineDash([]);
    const speech = (ag: OfficeAgent, text: string, side: number) => {
      if (!text) return;
      label(X, env, text, ag.x + (side < 0 ? -2 : 10), ag.y - 26, { color: INK, bg: "#ECE8E1", align: side < 0 ? "end" : "start", px: 7 });
    };
    speech(a, state.speech.a, a.x < b.x ? -1 : 1);
    speech(b, state.speech.b, b.x < a.x ? -1 : 1);
  }

  if (env.counter !== false) label(X, env, `${seatedCount(state)}/${MAX_DESKS} desks`, W - 4, H - 5, { color: "#7D869A", px: 8, align: "end" });
}

/** Agents with a desk (not walking out). */
export function seatedCount(state: OfficeState): number {
  return state.agents.filter((a) => a.activity !== "leaving").length;
}
export const DESK_COUNT = MAX_DESKS;

/** Logical centre of the desk an agent owns, for the hero's per-step pan. */
export function deskCentre(state: OfficeState, agentId: string): { x: number; y: number } | null {
  const a = state.agents.find((g) => g.id === agentId && g.activity !== "leaving");
  if (!a || a.deskIdx < 0) return null;
  const dk = state.desks[a.deskIdx];
  return { x: dk.x + 15, y: dk.y + 15 };
}
