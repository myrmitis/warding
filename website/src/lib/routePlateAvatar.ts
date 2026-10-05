/**
 * DiceBear style that generates route plates: a rounded signage tile in a transit
 * line colour, carrying a white route diagram.
 *
 * A DiceBear style is a plain object — `{ meta, schema, create({ prng, options }) }`
 * returning `{ attributes: { viewBox }, body }` — so this needs no dependency beyond
 * `@dicebear/core` and is consumed exactly like a published style pack.
 *
 * The diagram is wayfinding vocabulary on a 100x100 plate: a TRUNK line that enters
 * across one edge and bends only at 45° or 90°, up to two BRANCHES that leave the
 * trunk at a node, a STOP marker (an interchange ring or a station dot) on one node,
 * short station TICKS on straight runs, and an optional TERMINUS bar where the trunk
 * ends inside the plate. Every trunk is authored once, entering from the left, and
 * the seeded `turn` maps it through one of the square's eight symmetries, so six
 * shapes read as dozens.
 *
 * Legibility is the design constraint. The plate renders at 24–40px, so the route
 * is one thick stroke (11% of the edge), parallel runs keep a full grid step apart,
 * and a branch is only offered where it stays clear of the trunk
 * (`branchCandidates`). Every colour in `ROUTE_LINES` holds white at 3:1 or better
 * (WCAG non-text contrast), which the test asserts, so the route always reads
 * without an outline.
 *
 * DRAW ORDER IS PART OF EVERY AVATAR'S IDENTITY. The prng is a single stream and
 * each trait consumes exactly one step, so inserting a draw re-rolls every trait
 * after it and silently changes plates that already exist. Add new traits at the
 * END of `create`, never in the middle; the test pins the trait tuple of several
 * seeds to catch a violation. A trait an option overrides is still drawn, for the
 * same reason.
 */
import type { Style, StyleCreateProps } from '@dicebear/core'

type Point = readonly [number, number]

/** The ink every route mark is drawn in. */
const INK = '#ffffff'

/** Plate edge, in viewBox units. */
const PLATE = 100
/** Route stroke width. */
const LINE_W = 11
/** Corner radius of a bend, so a 45° or 90° turn reads as a track curve. */
const BEND_R = 10
/** Clear space a branch keeps from any other route stroke, centre to centre. */
const ROUTE_GAP = 17
/** Clear space a station tick keeps from any other route stroke. */
const TICK_GAP = 9
/** A branch shorter than this inside the plate reads as a blemish, not a line. */
const MIN_BRANCH_RUN = 16
/** Far enough past the plate edge that a line visibly runs off it. */
const RUN_OFF = 150
/** Sampling step for the clearance checks, in viewBox units. */
const STEP = 2

/**
 * Line colours, one per plate.
 *
 * Classic metro hues, each darkened until white on it clears 3:1, and spread so the
 * closest pair is still ~20 CIEDE2000 apart (both asserted by the test). The blue
 * is Junction's own signal accent.
 */
export const ROUTE_LINES: readonly string[] = [
  '#cf2a1f', // red
  '#dd6a00', // orange
  '#8a6d00', // gold
  '#1c8a3f', // green
  '#00808c', // teal
  '#1f55ec', // signal blue
  '#5b2a86', // violet
  '#c5227e', // magenta
]

/** A trunk node: a point on the line, and the line's unit direction there if straight. */
export interface RouteNode {
  p: Point
  /** Unit tangent on a straight run; null at a bend. */
  t: Point | null
}

/** A trunk as authored: entering from the left edge, nodes listed in path order. */
export interface Trunk {
  path: readonly Point[]
  nodes: readonly RouteNode[]
}

const D = Math.SQRT1_2
const E: Point = [1, 0]
const S: Point = [0, 1]
const SE: Point = [D, D]
const NE: Point = [D, -D]

export const TRUNKS = {
  straight: {
    path: [[-12, 50], [112, 50]],
    nodes: [{ p: [26, 50], t: E }, { p: [50, 50], t: E }, { p: [74, 50], t: E }],
  },
  step: {
    path: [[-12, 34], [34, 34], [66, 66], [112, 66]],
    nodes: [{ p: [18, 34], t: E }, { p: [50, 50], t: SE }, { p: [82, 66], t: E }],
  },
  hook: {
    path: [[-12, 34], [34, 34], [66, 66], [66, 112]],
    nodes: [{ p: [18, 34], t: E }, { p: [50, 50], t: SE }, { p: [66, 84], t: S }],
  },
  elbow: {
    path: [[-12, 42], [58, 42], [58, 112]],
    nodes: [{ p: [24, 42], t: E }, { p: [58, 42], t: null }, { p: [58, 76], t: S }],
  },
  chevron: {
    path: [[-12, 66], [18, 66], [50, 34], [82, 66], [112, 66]],
    nodes: [{ p: [34, 50], t: NE }, { p: [50, 34], t: null }, { p: [66, 50], t: SE }],
  },
  crank: {
    path: [[-12, 34], [42, 34], [42, 66], [112, 66]],
    nodes: [{ p: [20, 34], t: E }, { p: [42, 50], t: S }, { p: [74, 66], t: E }],
  },
} as const satisfies Record<string, Trunk>

export type TrunkName = keyof typeof TRUNKS

export type StopKind = 'ring' | 'dot'

/**
 * The square's eight symmetries as `[xx, xy, yx, yy]` about the plate centre:
 * four rotations, then four reflections.
 */
const TURNS: readonly (readonly [number, number, number, number])[] = [
  [1, 0, 0, 1],
  [0, -1, 1, 0],
  [-1, 0, 0, -1],
  [0, 1, -1, 0],
  [-1, 0, 0, 1],
  [1, 0, 0, -1],
  [0, 1, 1, 0],
  [0, -1, -1, 0],
]

/* ---------- geometry ---------- */

const sub = (a: Point, b: Point): Point => [a[0] - b[0], a[1] - b[1]]
const add = (a: Point, b: Point): Point => [a[0] + b[0], a[1] + b[1]]
const scale = (a: Point, k: number): Point => [a[0] * k, a[1] * k]
const len = (a: Point): number => Math.hypot(a[0], a[1])
const unit = (a: Point): Point => scale(a, 1 / len(a))
const same = (a: Point, b: Point): boolean =>
  Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6

function distToSegment(p: Point, a: Point, b: Point): number {
  const ab = sub(b, a)
  const k = Math.max(0, Math.min(1, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / (len(ab) ** 2)))
  return len(sub(p, add(a, scale(ab, k))))
}

type Segment = readonly [Point, Point]

const segmentsOf = (path: readonly Point[]): Segment[] =>
  path.slice(1).map((b, i) => [path[i], b] as const)

/** Which segments of `path` the point lies on (one on a run, two at a vertex). */
function segmentsAt(path: readonly Point[], p: Point): number[] {
  return segmentsOf(path)
    .map((s, i) => (distToSegment(p, s[0], s[1]) < 1e-6 ? i : -1))
    .filter((i) => i >= 0)
}

/** Distance along `d` from `p` to where it leaves the plate. */
function runInside(p: Point, d: Point): number {
  let s = 0
  while (s < RUN_OFF) {
    const q = add(p, scale(d, s + STEP))
    if (q[0] < 0 || q[0] > PLATE || q[1] < 0 || q[1] > PLATE) break
    s += STEP
  }
  return s
}

/** Sample points along `a → b` from `from` units in, stopping at the plate edge. */
function samples(a: Point, b: Point, from: number): Point[] {
  const d = unit(sub(b, a))
  const n = Math.min(len(sub(b, a)), runInside(a, d) + STEP)
  const out: Point[] = []
  for (let s = from; s <= n; s += STEP) out.push(add(a, scale(d, s)))
  return out
}

const clearOf = (pts: Point[], segs: readonly Segment[], gap: number): boolean =>
  pts.every((q) => segs.every(([a, b]) => distToSegment(q, a, b) >= gap))

/** Eight compass directions, clockwise from east. */
const DIRS: readonly Point[] = [E, SE, S, [-D, D], [-1, 0], [-D, -D], [0, -1], NE]

/** A place a branch may leave the trunk: which node, and which way. */
export interface BranchCandidate {
  node: number
  dir: Point
}

/**
 * Every branch the trunk can carry without crowding it, in a stable order.
 *
 * A direction is offered only when it is not along the trunk at that node, the
 * branch stays `ROUTE_GAP` clear of every trunk segment it does not leave from
 * (right from the node) and of the segments it does leave from (once it has
 * diverged), and it runs long enough inside the plate to read as a line.
 */
export function branchCandidates(trunk: Trunk): BranchCandidate[] {
  const segs = segmentsOf(trunk.path)
  const out: BranchCandidate[] = []
  trunk.nodes.forEach((node, index) => {
    const own = segmentsAt(trunk.path, node.p)
    const along = own.flatMap((i) => {
      const u = unit(sub(segs[i][1], segs[i][0]))
      return [u, scale(u, -1)]
    })
    const others = segs.filter((_, i) => !own.includes(i))
    const mine = own.map((i) => segs[i])
    for (const dir of DIRS) {
      if (along.some((u) => same(u, dir))) continue
      if (runInside(node.p, dir) < MIN_BRANCH_RUN) continue
      const end = add(node.p, scale(dir, RUN_OFF))
      // Checked from just past the node's own marker for the rest of the trunk, and
      // from 26 units for the run it leaves: diverging at 45° needs ~24 before the
      // two strokes separate.
      if (!clearOf(samples(node.p, end, 12), others, ROUTE_GAP)) continue
      if (!clearOf(samples(node.p, end, 26), mine, ROUTE_GAP)) continue
      out.push({ node: index, dir })
    }
  })
  return out
}

const CANDIDATES: Record<TrunkName, BranchCandidate[]> = Object.fromEntries(
  (Object.keys(TRUNKS) as TrunkName[]).map((k) => [k, branchCandidates(TRUNKS[k])]),
) as Record<TrunkName, BranchCandidate[]>

/* ---------- traits ---------- */

/**
 * Weighted pick lists. Repeating an entry IS how DiceBear expresses weight — there
 * is no probability parameter.
 */
const TRUNK_PICKS: TrunkName[] = [
  'straight',
  'step',
  'step',
  'hook',
  'hook',
  'elbow',
  'elbow',
  'chevron',
  'crank',
]
const BRANCH_COUNT_PICKS = [0, 0, 0, 1, 1, 1, 2]
const STOP_PICKS: StopKind[] = ['ring', 'ring', 'dot']
const TICK_COUNT_PICKS = [0, 0, 1, 2]
/** Wide enough that an index modulo any candidate count stays uniform. */
const INDEX_MAX = 999

export interface RoutePlateOptions {
  /**
   * Pins the line colour to `ROUTE_LINES[line]` (wrapped), keeping every other trait
   * seeded. Null or absent lets the seed choose.
   */
  line: number | null
}

/** The drawn traits. Indices are resolved against the trunk by `compose`. */
export interface RoutePlateTraits {
  line: string
  trunk: TrunkName
  /** Index into the square's eight symmetries. */
  turn: number
  /** Branches asked for (0–2); fewer are drawn when the trunk has no room. */
  branches: number
  branchA: number
  branchB: number
  stop: StopKind
  /** Node for the stop marker when no branch claims one. */
  stopAt: number
  ticks: number
  /** Which side of the line station ticks hang on: 1 or -1. */
  tickSide: number
  terminus: boolean
}

/** Wrap any finite integer onto the line palette, folding negatives. */
export function lineAt(index: number): string {
  const n = ROUTE_LINES.length
  return ROUTE_LINES[((Math.trunc(index) % n) + n) % n]
}

/* ---------- rendering ---------- */

const num = (n: number): string => String(Math.round(n * 10) / 10)

/** A polyline with each corner eased into a quadratic curve. */
function routePath(pts: readonly Point[]): string {
  let d = `M${num(pts[0][0])} ${num(pts[0][1])}`
  for (let i = 1; i < pts.length - 1; i++) {
    const inU = unit(sub(pts[i], pts[i - 1]))
    const outU = unit(sub(pts[i + 1], pts[i]))
    const r = Math.min(BEND_R, len(sub(pts[i], pts[i - 1])) / 2, len(sub(pts[i + 1], pts[i])) / 2)
    const a = sub(pts[i], scale(inU, r))
    const b = add(pts[i], scale(outU, r))
    d += `L${num(a[0])} ${num(a[1])}Q${num(pts[i][0])} ${num(pts[i][1])} ${num(b[0])} ${num(b[1])}`
  }
  const last = pts[pts.length - 1]
  return `${d}L${num(last[0])} ${num(last[1])}`
}

/**
 * One self-closing SVG element from its attributes. Markup is assembled from data
 * rather than written as template text, so every literal here is an attribute value
 * handed to the SVG parser — never words anyone reads.
 */
function svgEl(tag: string, attrs: Record<string, string | number>): string {
  const body = Object.entries(attrs).map(([k, v]) => k + '="' + v + '"')
  return '<' + [tag, ...body].join(' ') + '/>'
}

const stroke = (d: string, width: number, cap: 'round' | 'butt'): string =>
  svgEl('path', {
    d,
    fill: 'none',
    stroke: INK,
    'stroke-width': width,
    'stroke-linecap': cap,
    'stroke-linejoin': 'round',
  })

const disc = (p: Point, r: number, fill: string): string =>
  svgEl('circle', { cx: num(p[0]), cy: num(p[1]), r, fill })

/**
 * The only composition path. `create` calls it with prng-drawn traits and tests
 * call it with explicit ones, so a fixture cannot drift from real output.
 */
export function compose(t: RoutePlateTraits): string {
  const trunk: Trunk = TRUNKS[t.trunk] ?? TRUNKS.straight
  const cands = CANDIDATES[t.trunk] ?? []
  const segs = segmentsOf(trunk.path)
  const [xx, xy, yx, yy] = TURNS[((t.turn % 8) + 8) % 8]
  const at = (p: Point): Point => {
    const x = p[0] - PLATE / 2
    const y = p[1] - PLATE / 2
    return [xx * x + xy * y + PLATE / 2, yx * x + yy * y + PLATE / 2]
  }

  // Branches: the first asked-for candidate, then the next one that keeps its
  // distance from it. Walking the list instead of re-drawing keeps the stream fixed.
  const branches: BranchCandidate[] = []
  if (t.branches >= 1 && cands.length > 0) branches.push(cands[t.branchA % cands.length])
  if (t.branches >= 2 && branches.length === 1) {
    const first = branches[0]
    const firstRay: Segment = [trunk.nodes[first.node].p, add(trunk.nodes[first.node].p, scale(first.dir, RUN_OFF))]
    for (let k = 0; k < cands.length; k++) {
      const c = cands[(t.branchB + k) % cands.length]
      if (c.node === first.node) continue
      const from = trunk.nodes[c.node].p
      if (clearOf(samples(from, add(from, scale(c.dir, RUN_OFF)), 0), [firstRay], ROUTE_GAP)) {
        branches.push(c)
        break
      }
    }
  }
  const branchRays: Segment[] = branches.map((b) => {
    const p = trunk.nodes[b.node].p
    return [p, add(p, scale(b.dir, RUN_OFF))]
  })
  const branchNodes = new Set(branches.map((b) => b.node))
  const stopNode = branches.length > 0 ? branches[0].node : t.stopAt % trunk.nodes.length

  // Terminus: the trunk stops at its first node instead of running off the plate.
  let path: readonly Point[] = trunk.path
  const head = trunk.nodes[0]
  if (t.terminus) {
    const [first] = segmentsAt(trunk.path, head.p)
    path = [head.p, ...trunk.path.slice(first + 1).filter((p) => !same(p, head.p))]
  }
  const capped = t.terminus && head.t !== null && stopNode !== 0 && !branchNodes.has(0)

  // Station ticks: straight nodes only, clear of every other mark.
  const ticks: Segment[] = []
  trunk.nodes.forEach((node, index) => {
    if (ticks.length >= t.ticks || node.t === null) return
    if (index === stopNode || branchNodes.has(index) || (t.terminus && index === 0)) return
    const n: Point = scale([-node.t[1], node.t[0]], t.tickSide < 0 ? -1 : 1)
    const tick: Segment = [add(node.p, scale(n, LINE_W / 2 - 1)), add(node.p, scale(n, LINE_W / 2 + 10))]
    const others = segs.filter((_, i) => !segmentsAt(trunk.path, node.p).includes(i))
    if (!clearOf(samples(tick[0], tick[1], 2), [...others, ...branchRays], TICK_GAP)) return
    ticks.push(tick)
  })

  const parts = [
    svgEl('rect', { width: PLATE, height: PLATE, fill: t.line }),
    stroke(routePath(path.map(at)), LINE_W, 'round'),
    ...branchRays.map(([a, b]) => stroke(routePath([at(a), at(b)]), LINE_W, 'round')),
    ...ticks.map(([a, b]) => stroke(routePath([at(a), at(b)]), 7, 'butt')),
  ]
  if (capped && head.t) {
    const n: Point = [-head.t[1], head.t[0]]
    parts.push(stroke(routePath([at(add(head.p, scale(n, 11))), at(sub(head.p, scale(n, 11)))]), 9, 'round'))
  }
  const stop = at(trunk.nodes[stopNode].p)
  parts.push(
    t.stop === 'ring' ? disc(stop, 13, INK) + disc(stop, 6.5, t.line) : disc(stop, 9.5, INK),
  )
  return parts.join('')
}

export const routePlate: Style<RoutePlateOptions> = {
  /**
   * `creator` only, deliberately. `@dicebear/core` always emits a Dublin Core
   * metadata block, and its rights line prefixes "Remix of" whenever a `title` is
   * set and the license is not MIT — which would put a false remix claim in every
   * avatar, since this art is first-party.
   */
  meta: { creator: 'Junction' },
  schema: {
    properties: {
      line: { type: ['integer', 'null'], default: null },
    },
  },
  create({ prng, options }: StyleCreateProps<RoutePlateOptions>) {
    // Draw order is frozen: append new traits below `terminus`, never above.
    const drawnLine = prng.pick([...ROUTE_LINES], ROUTE_LINES[0])
    const trunk = prng.pick(TRUNK_PICKS, 'straight')
    const turn = prng.integer(0, TURNS.length - 1)
    const branches = prng.pick(BRANCH_COUNT_PICKS, 0)
    const branchA = prng.integer(0, INDEX_MAX)
    const branchB = prng.integer(0, INDEX_MAX)
    const stop = prng.pick(STOP_PICKS, 'ring')
    const stopAt = prng.integer(0, INDEX_MAX)
    const ticks = prng.pick(TICK_COUNT_PICKS, 0)
    const tickSide = prng.bool(50) ? 1 : -1
    const terminus = prng.bool(35)

    const pinned = options.line
    const traits: RoutePlateTraits = {
      line: typeof pinned === 'number' && Number.isFinite(pinned) ? lineAt(pinned) : drawnLine,
      trunk,
      turn,
      branches,
      branchA,
      branchB,
      stop,
      stopAt,
      ticks,
      tickSide,
      terminus,
    }
    return {
      attributes: { viewBox: `0 0 ${PLATE} ${PLATE}` },
      body: compose(traits),
      extra: () => ({ ...traits }),
    }
  },
}
