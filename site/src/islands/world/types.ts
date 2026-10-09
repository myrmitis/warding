/**
 * The product's `AgentSource` shape (website/src/hooks/useAgentSync.ts), plus one
 * site-only extension: `refused` names a command the gate refused, which the
 * renderer shows as the sprite frozen in the seal colour. The dashboard does not
 * carry that field yet; the hero timeline is scripted and labelled as such.
 */
export interface AgentSource {
  id: string;
  name: string;
  label: string;
  kind: "slot" | "cron" | "spawn";
  running: boolean;
  detail: string;
  /** Latest message preview for chat slots (empty for crons/spawns). */
  lastMessage?: string;
  /** True when the session is waiting for user input. */
  waitingForInput?: boolean;
  /** Pending tool approval blocking the session, if any. */
  pendingApproval?: { tool: string; requestId: string } | null;
  /** Site extension: the command the gate refused (sprite freezes, seal colour). */
  refused?: string;
}

/** A minimal 2D context: what the renderer actually calls. Satisfied by a real
 *  CanvasRenderingContext2D and by the build-time SVG recorder used for OG images. */
export interface Ctx {
  fillStyle: string | CanvasGradient | CanvasPattern;
  strokeStyle: string | CanvasGradient | CanvasPattern;
  lineWidth: number;
  font: string;
  textAlign: CanvasTextAlign;
  textBaseline: CanvasTextBaseline;
  globalAlpha: number;
  fillRect(x: number, y: number, w: number, h: number): void;
  clearRect(x: number, y: number, w: number, h: number): void;
  beginPath(): void;
  closePath(): void;
  ellipse(x: number, y: number, rx: number, ry: number, rot: number, a0: number, a1: number): void;
  fill(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  stroke(): void;
  setLineDash(segments: number[]): void;
  createRadialGradient(x0: number, y0: number, r0: number, x1: number, y1: number, r1: number): CanvasGradient;
  fillText(text: string, x: number, y: number): void;
  measureText(text: string): { width: number };
  save(): void;
  restore(): void;
}
