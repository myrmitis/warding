import { useCallback, useEffect, useRef, useState } from "react";
import { ImageDown, Pause, Play } from "lucide-react";
import { applySources, createOffice, deskCentre, draw, seatedCount, update, DESK_COUNT, H, TICKS_PER_SECOND, W } from "./office";
import { BEATS, REDUCED_MOTION_STEP, resolvedBeat } from "./timeline";
import { track } from "../../lib/analytics";

/**
 * The live hero world: the shipping Office renderer fed a scripted timeline.
 *
 * - integer scaling only: always 2x, cropped to the column. The crop keeps the
 *   wall (its lit window, clock and whiteboard are the most legible part of the
 *   scene) unless `showWall` is false, and pans to the acting sprite's desk on
 *   each step (400 ms; instant under reduced motion)
 * - time-based tick at 30/s; paused off-screen, on hidden tabs, and by the
 *   visible 44 px Pause/Play control (state kept in localStorage, try/catch)
 * - prefers-reduced-motion draws once at 02:30 with the refused state; the
 *   control then reads "Play" and is the visitor's opt-in
 * - follows the page's `warding:step` events; auto-cycles the night on step 0
 * - "Save tonight as a wallpaper": a 44 px icon button beside Pause; a PNG of this
 *   simulated frame at 2x with the local time and the lit-window glyph stamped
 *   bottom-right
 */
interface Props { label?: string; showWall?: boolean }

const PAUSE_KEY = "warding.world.paused";
const CYCLE_MS = 9000;
const SCALE = 2;
/** Logical y where the wall trim ends and the floor begins; the floor-only crop starts here. */
const FLOOR_Y = 80;
/** Logical y the wall crop starts at: just above the window and whiteboard frames. */
const WALL_Y = 6;

type Layout = { frameW: number; frameH: number; top: number };
type Point = { x: number; y: number };

function measure(width: number, showWall: boolean): Layout {
  const top = showWall ? WALL_Y : FLOOR_Y;
  const frameW = Math.max(240, Math.min(W * SCALE, Math.floor(width)));
  return { frameW, frameH: (H - top) * SCALE, top };
}

/** Offset of the 2x canvas inside the frame so `focus` (logical) sits centred, clamped to the floor. */
function panTo(layout: Layout, focus: Point | null): Point {
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  const fx = focus ? focus.x * SCALE - layout.frameW / 2 : 0;
  const fy = focus ? focus.y * SCALE - layout.frameH / 2 : 0;
  return {
    x: Math.round(clamp(fx, 0, W * SCALE - layout.frameW)),
    y: Math.round(clamp(fy, layout.top * SCALE, H * SCALE - layout.frameH)),
  };
}

function localTime(): string {
  try {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());
  } catch {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
}

export default function OfficeWorld({ label = "Pixel-art night office: agent sprites at their desks, one waiting on an approval. A simulated demo drawn by the product's own renderer.", showWall = true }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(createOffice(Math.floor(Math.random() * 1e6)));
  const tickRef = useRef(0);
  const stepRef = useRef(0);
  const visibleRef = useRef(true);
  const pausedRef = useRef(false);
  const reducedRef = useRef(false);
  const dprRef = useRef(1);
  const [layout, setLayout] = useState<Layout>(() => measure(W * SCALE, showWall));
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [time, setTime] = useState("");
  const [saved, setSaved] = useState("");
  const [focus, setFocus] = useState<Point | null>(null);
  const [seated, setSeated] = useState(0);

  const render = useCallback(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const S = SCALE * dprRef.current;
    const now = new Date();
    draw(stateRef.current, ctx, { S, textScale: dprRef.current, hour: now.getHours(), minute: now.getMinutes(), counter: false }, tickRef.current);
  }, []);

  const applyBeat = useCallback((step: number, instant = false) => {
    const beat = BEATS[Math.max(0, Math.min(BEATS.length - 1, step))];
    stepRef.current = beat.step;
    applySources(stateRef.current, beat.sources, { instant, reenter: beat.reenter, tick: tickRef.current });
    if (instant) for (let i = 0; i < 30; i++) update(stateRef.current, ++tickRef.current);
    setFocus(deskCentre(stateRef.current, beat.focus));
    setSeated(seatedCount(stateRef.current));
  }, []);

  // Layout: integer scale from the container width; buffer sized for the DPR.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    dprRef.current = Math.min(2, Math.ceil(window.devicePixelRatio || 1));
    const apply = () => setLayout(measure(wrap.clientWidth, showWall));
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [showWall]);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const S = SCALE * dprRef.current;
    c.width = W * S;
    c.height = H * S;
    const ctx = c.getContext("2d");
    if (ctx) ctx.imageSmoothingEnabled = false;
    render();
  }, [layout, render]);

  // Initial state, pause memory, reduced motion.
  useEffect(() => {
    let p = false;
    try { p = localStorage.getItem(PAUSE_KEY) === "1"; } catch { /* no storage */ }
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    reducedRef.current = rm;
    setReduced(rm);
    pausedRef.current = p;
    setPaused(p);
    applyBeat(rm ? REDUCED_MOTION_STEP : 0, true);
    render();
    setTime(localTime());
    const id = window.setInterval(() => setTime(localTime()), 20000);
    return () => window.clearInterval(id);
  }, [applyBeat, render]);

  // The loop: 30 ticks per second on a time base, only while something can be seen.
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const dt = 1000 / TICKS_PER_SECOND;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const live = !pausedRef.current && !reducedRef.current && visibleRef.current && !document.hidden;
      if (!live) { last = now; acc = 0; return; }
      acc += now - last; last = now;
      let steps = 0;
      while (acc >= dt && steps < 4) { acc -= dt; update(stateRef.current, ++tickRef.current); steps++; }
      if (acc > dt * 4) acc = 0;
      if (steps) render();
    };
    raf = requestAnimationFrame(frame);
    const onVis = () => { if (!document.hidden) render(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelAnimationFrame(raf); document.removeEventListener("visibilitychange", onVis); };
  }, [render]);

  // Off-screen pause.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((entries) => { visibleRef.current = entries.some((e) => e.isIntersecting); }, { threshold: 0.05 });
    io.observe(wrap);
    return () => io.disconnect();
  }, []);

  // Page steps and the approve demo drive the beats; step 0 cycles the night.
  useEffect(() => {
    let cycle = 0;
    const startCycle = () => {
      window.clearInterval(cycle);
      cycle = window.setInterval(() => {
        if (pausedRef.current || reducedRef.current || !visibleRef.current || document.hidden) return;
        const next = (stepRef.current + 1) % BEATS.length;
        applyBeat(next);
      }, CYCLE_MS);
    };
    const onStep = (e: Event) => {
      const step = Number((e as CustomEvent<{ step: number }>).detail?.step ?? 0);
      if (step === 0) { if (stepRef.current !== 0) applyBeat(0); startCycle(); return; }
      window.clearInterval(cycle);
      if (step !== stepRef.current) applyBeat(step, reducedRef.current);
      if (reducedRef.current) render();
    };
    const onApproval = (e: Event) => {
      const action = (e as CustomEvent<{ action: "approve" | "deny" }>).detail?.action;
      if (!action) return;
      applySources(stateRef.current, resolvedBeat(action).sources, { tick: tickRef.current });
      if (reducedRef.current) render();
    };
    window.addEventListener("warding:step", onStep);
    window.addEventListener("warding:approval", onApproval);
    startCycle();
    return () => { window.clearInterval(cycle); window.removeEventListener("warding:step", onStep); window.removeEventListener("warding:approval", onApproval); };
  }, [applyBeat, render]);

  const togglePause = () => {
    // Under reduced motion the first press is the opt-in to motion.
    if (reducedRef.current) { reducedRef.current = false; setReduced(false); applyBeat(stepRef.current); pausedRef.current = false; setPaused(false); track("pause_toggle", { state: "play" }); return; }
    const next = !pausedRef.current;
    pausedRef.current = next;
    setPaused(next);
    try { localStorage.setItem(PAUSE_KEY, next ? "1" : "0"); } catch { /* fine */ }
    track("pause_toggle", { state: next ? "pause" : "play" });
  };

  const saveWallpaper = () => {
    try {
      const S = 4; // 2x at DPR 2
      const off = document.createElement("canvas");
      off.width = W * S; off.height = H * S;
      const ctx = off.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      const now = new Date();
      draw(stateRef.current, ctx, { S, textScale: 2, hour: now.getHours(), minute: now.getMinutes(), counter: false }, tickRef.current);
      // Stamp: local time + the lit-window glyph, bottom-right.
      const t = localTime();
      ctx.font = `${22 * 2}px "Departure Mono", "IBM Plex Mono", monospace`;
      ctx.textAlign = "right"; ctx.textBaseline = "alphabetic";
      ctx.fillStyle = "#FFB547";
      ctx.fillText(t, off.width - 22 * S, off.height - 6 * S);
      const gx = off.width - 16 * S, gy = off.height - 20 * S, g = 12 * S;
      ctx.fillStyle = "#9AA3B5"; ctx.fillRect(gx, gy, g, g);
      ctx.fillStyle = "#0B0E14"; ctx.fillRect(gx + 2, gy + 2, g / 2 - 3, g / 2 - 3); ctx.fillRect(gx + g / 2 + 1, gy + 2, g / 2 - 3, g / 2 - 3); ctx.fillRect(gx + 2, gy + g / 2 + 1, g / 2 - 3, g / 2 - 3);
      ctx.fillStyle = "#FFB547"; ctx.fillRect(gx + g / 2 + 1, gy + g / 2 + 1, g / 2 - 3, g / 2 - 3);
      off.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `warding-night-${t.replace(":", "")}.png`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        setSaved(`Saved warding-night-${t.replace(":", "")}.png`);
        track("wallpaper_save");
      }, "image/png");
    } catch {
      setSaved("Could not export this frame in this browser.");
    }
  };

  const playing = !paused && !reduced;
  const off = panTo(layout, focus);
  const frameStyle = { width: layout.frameW, height: layout.frameH };
  const canvasStyle = {
    width: W * SCALE,
    height: H * SCALE,
    transform: `translate(${-off.x}px, ${-off.y}px)`,
    transition: reduced ? "none" : "transform 400ms cubic-bezier(.22,1,.36,1)",
  };

  return (
    <div className="world" data-live ref={wrapRef}>
      <div className="world-frame" style={frameStyle}>
        <canvas ref={canvasRef} className="world-canvas" role="img" aria-label={label} style={canvasStyle} />
        {seated > 0 && <span className="world-count">{seated}/{DESK_COUNT} desks</span>}
        <div className="world-chip">
          <span className="chip">Simulated demo · real renderer · {time ? `${time} your time` : "your time"}</span>
          <span className="world-controls">
            <button type="button" className="world-btn" onClick={saveWallpaper} aria-label="Save tonight as a wallpaper" title="Save tonight as a wallpaper">
              <ImageDown className="lucide" aria-hidden="true" />
            </button>
            <button type="button" className="world-btn" onClick={togglePause} aria-label={playing ? "Pause" : "Play"} aria-pressed={!playing}>
              {playing ? <Pause className="lucide" aria-hidden="true" /> : <Play className="lucide" aria-hidden="true" />}
            </button>
          </span>
        </div>
      </div>
      <span className="sr-only" aria-live="polite">{saved}</span>
    </div>
  );
}
