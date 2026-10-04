import { useEffect, useRef } from "react";
import { drawSprite } from "./office";

/**
 * A margin drollery: a tiny pixel agent on a small canvas, drawn by the same
 * sprite code as the world, in the paper plates' three-ink set. Each performs
 * once for under five seconds when it scrolls into view, then rests, so no
 * pause control is owed (WCAG 2.2.2); static under reduced motion. At most
 * three per page (brand-book §12).
 *
 *  bounce   — climbs toward the margin rule (the policy file) and bounces off
 *  sleep    — dozes on the schedule article
 *  envelope — carries an entry to the audit chain
 */
type Kind = "bounce" | "sleep" | "envelope";
interface Props { kind: Kind; label?: string }

const LW = 120, LH = 56, SCALE = 2;
const INK = "#1A1814", SEAL = "#B3301A", MARKER = "#F5D547", PAPER = "#F3EEE3";
const DURATION_TICKS = 4.5 * 30;

function scene(kind: Kind, t: number, ctx: CanvasRenderingContext2D, dpr: number) {
  const S = SCALE * dpr;
  ctx.clearRect(0, 0, LW * S, LH * S);
  const d = (x: number, y: number, w: number, h: number, c: string) => { ctx.fillStyle = c; ctx.fillRect(x * S, y * S, w * S, h * S); };
  const done = t >= DURATION_TICKS;
  // Floor rule
  d(0, 46, LW, 1, "#D9D0BF");
  if (kind === "bounce") {
    // The margin rule stands in for the policy file: a tall line with a file tab.
    d(92, 6, 2, 40, SEAL); d(94, 8, 10, 12, PAPER); d(94, 8, 10, 1, INK); d(94, 19, 10, 1, INK); d(103, 8, 1, 12, INK); d(96, 11, 6, 1, INK); d(96, 14, 6, 1, INK);
    let x: number, dir = 1, moving = true;
    const hit = 60; // tick at which it reaches the rule
    if (done) { x = 30; dir = 1; moving = false; }
    else if (t < hit) { x = 8 + (t / hit) * 74; }
    else if (t < hit + 12) { x = 82 - (t - hit) * 2.2; dir = -1; moving = true; d(84, 12, 1, 1, SEAL); d(86, 10, 1, 1, SEAL); d(88, 13, 1, 1, SEAL); }
    else { x = Math.max(30, 56 - (t - hit - 12) * 0.9); dir = x > 30 ? -1 : 1; moving = x > 30; }
    drawSprite(ctx, S, x, 34, { color: MARKER, t, moving, dir, ink: INK, skin: PAPER });
  } else if (kind === "sleep") {
    // A desk edge and a mug; the sprite dozes.
    d(60, 38, 40, 8, "#D9D0BF"); d(64, 32, 4, 5, SEAL); d(68, 33, 1, 3, SEAL);
    drawSprite(ctx, S, 40, 34, { color: MARKER, t: done ? DURATION_TICKS : t, moving: false, dir: 1, asleep: true, ink: INK, skin: PAPER });
  } else {
    // Three chained blocks: the audit log.
    for (let i = 0; i < 3; i++) { d(86 + i * 11, 30, 8, 8, i === 2 ? SEAL : INK); if (i < 2) d(94 + i * 11, 33, 3, 2, INK); }
    const end = 70;
    const x = done ? end : Math.min(end, 6 + (t / 100) * (end - 6));
    drawSprite(ctx, S, x, 34, { color: MARKER, t, moving: x < end, dir: 1, carry: "envelope", ink: INK, skin: PAPER });
  }
}

export default function Drollery({ kind, label }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = Math.min(2, Math.ceil(window.devicePixelRatio || 1));
    c.width = LW * SCALE * dpr; c.height = LH * SCALE * dpr;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) { scene(kind, DURATION_TICKS, ctx, dpr); return; }
    scene(kind, 0, ctx, dpr);
    let raf = 0, started = 0, playedOnce = false;
    const run = (now: number) => {
      if (!started) started = now;
      const t = Math.floor(((now - started) / 1000) * 30);
      scene(kind, t, ctx, dpr);
      if (t < DURATION_TICKS) raf = requestAnimationFrame(run);
    };
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && !playedOnce) { playedOnce = true; raf = requestAnimationFrame(run); io.disconnect(); }
    }, { threshold: 0.4 });
    io.observe(c);
    return () => { cancelAnimationFrame(raf); io.disconnect(); };
  }, [kind]);
  return (
    <canvas
      ref={ref}
      className="drollery"
      style={{ width: LW * SCALE, height: LH * SCALE, imageRendering: "pixelated" }}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}
