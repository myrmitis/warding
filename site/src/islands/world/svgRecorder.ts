import type { Ctx } from "./types";

/**
 * A 2D-context stand-in that records fills as SVG so the office renderer can
 * draw a frame at build time (OG images) with no canvas dependency. Gradients
 * and text are dropped: the frame is a plate, not a screenshot.
 */
export class SvgRecorder implements Ctx {
  fillStyle: Ctx["fillStyle"] = "#000";
  strokeStyle: Ctx["strokeStyle"] = "#000";
  lineWidth = 1;
  font = "";
  textAlign: CanvasTextAlign = "start";
  textBaseline: CanvasTextBaseline = "alphabetic";
  globalAlpha = 1;
  private parts: string[] = [];
  private path: { kind: "ellipse"; x: number; y: number; rx: number; ry: number }[] = [];
  private line: number[][] = [];

  private colour(c: Ctx["fillStyle"]): string | null {
    if (typeof c !== "string") return null;
    return c;
  }
  private alpha(): string {
    return this.globalAlpha < 1 ? ` opacity="${this.globalAlpha.toFixed(2)}"` : "";
  }
  fillRect(x: number, y: number, w: number, h: number) {
    const c = this.colour(this.fillStyle);
    if (!c || w <= 0 || h <= 0) return;
    this.parts.push(`<rect x="${r(x)}" y="${r(y)}" width="${r(w)}" height="${r(h)}" fill="${c}"${this.alpha()}/>`);
  }
  clearRect() {}
  beginPath() { this.path = []; this.line = []; }
  closePath() {}
  ellipse(x: number, y: number, rx: number, ry: number) { this.path.push({ kind: "ellipse", x, y, rx, ry }); }
  fill() {
    const c = this.colour(this.fillStyle);
    if (!c) return;
    this.path.forEach((p) => this.parts.push(`<ellipse cx="${r(p.x)}" cy="${r(p.y)}" rx="${r(p.rx)}" ry="${r(p.ry)}" fill="${c}"/>`));
    this.path = [];
  }
  moveTo(x: number, y: number) { this.line = [[x, y]]; }
  lineTo(x: number, y: number) { this.line.push([x, y]); }
  stroke() {
    const c = this.colour(this.strokeStyle);
    if (!c || this.line.length < 2) return;
    const d = this.line.map(([x, y], i) => `${i ? "L" : "M"}${r(x)} ${r(y)}`).join(" ");
    this.parts.push(`<path d="${d}" stroke="${c}" stroke-width="${r(this.lineWidth)}" fill="none"/>`);
  }
  setLineDash() {}
  createRadialGradient(): CanvasGradient {
    return { addColorStop() {} } as unknown as CanvasGradient;
  }
  fillText() {}
  measureText(text: string) { return { width: text.length * 6 }; }
  save() {}
  restore() { this.globalAlpha = 1; }
  toSvgGroup(): string { return this.parts.join(""); }
}

const r = (n: number) => Math.round(n * 100) / 100;
