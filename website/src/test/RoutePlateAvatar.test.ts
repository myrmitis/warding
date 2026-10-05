/**
 * Guards for the generated route-plate avatars.
 *
 * Four properties here are load-bearing and cannot be checked by eye:
 *  - every line colour holds white at WCAG non-text contrast (3:1) and stays under
 *    L* 78, because the whole route is drawn in white with no outline;
 *  - line colours keep a minimum CIEDE2000 distance, so two plates never read as
 *    the same line drawn twice;
 *  - no branch the generator can offer crosses its trunk, and every node leaves room
 *    for a full interchange ring inside the plate;
 *  - the prng draw ORDER is frozen, because the stream is positional: inserting a
 *    draw re-rolls every trait after it and silently changes existing plates.
 */
import { describe, it, expect } from 'vitest'
import { createAvatar } from '@dicebear/core'
import {
  routePlate,
  compose,
  branchCandidates,
  lineAt,
  ROUTE_LINES,
  TRUNKS,
  type RoutePlateTraits,
  type TrunkName,
} from '../lib/routePlateAvatar'

/* ---------- colour maths, for the palette guards only ---------- */

const channels = (hex: string): number[] =>
  [0, 2, 4].map((i) => parseInt(hex.replace('#', '').slice(i, i + 2), 16) / 255)
const linear = (v: number): number => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map(linear)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function rgbToLab(hex: string): [number, number, number] {
  const [r, g, b] = channels(hex).map(linear)
  const x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
  const y = r * 0.2126729 + g * 0.7151522 + b * 0.072175
  const z = (r * 0.0193339 + g * 0.119192 + b * 0.9503041) / 1.08883
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29)
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))]
}

function deltaE00(c1: string, c2: string): number {
  const [L1, a1, b1] = rgbToLab(c1)
  const [L2, a2, b2] = rgbToLab(c2)
  const rad = Math.PI / 180
  const Cb = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2
  const G = 0.5 * (1 - Math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
  const ap1 = a1 * (1 + G)
  const ap2 = a2 * (1 + G)
  const Cp1 = Math.hypot(ap1, b1)
  const Cp2 = Math.hypot(ap2, b2)
  const hp1 = (Math.atan2(b1, ap1) / rad + 360) % 360
  const hp2 = (Math.atan2(b2, ap2) / rad + 360) % 360
  const dL = L2 - L1
  const dC = Cp2 - Cp1
  let dh = 0
  if (Cp1 * Cp2 !== 0) {
    dh = hp2 - hp1
    if (dh > 180) dh -= 360
    else if (dh < -180) dh += 360
  }
  const dH = 2 * Math.sqrt(Cp1 * Cp2) * Math.sin((dh * rad) / 2)
  const Lb = (L1 + L2) / 2
  const Cpb = (Cp1 + Cp2) / 2
  let hpb = hp1 + hp2
  if (Cp1 * Cp2 !== 0) {
    if (Math.abs(hp1 - hp2) > 180) hpb += hpb < 360 ? 360 : -360
    hpb /= 2
  }
  const T =
    1 -
    0.17 * Math.cos((hpb - 30) * rad) +
    0.24 * Math.cos(2 * hpb * rad) +
    0.32 * Math.cos((3 * hpb + 6) * rad) -
    0.2 * Math.cos((4 * hpb - 63) * rad)
  const dTheta = 30 * Math.exp(-(((hpb - 275) / 25) ** 2))
  const Rc = 2 * Math.sqrt(Cpb ** 7 / (Cpb ** 7 + 25 ** 7))
  const Sl = 1 + (0.015 * (Lb - 50) ** 2) / Math.sqrt(20 + (Lb - 50) ** 2)
  const Sc = 1 + 0.045 * Cpb
  const Sh = 1 + 0.015 * Cpb * T
  const Rt = -Math.sin(2 * dTheta * rad) * Rc
  return Math.sqrt(
    (dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rt * (dC / Sc) * (dH / Sh),
  )
}

/* ---------- geometry, computed independently of the module ---------- */

type P = readonly [number, number]

/** Proper intersection of two segments (touching at an endpoint does not count). */
function crosses(a: P, b: P, c: P, d: P): boolean {
  const cross = (o: P, p: P, q: P) => (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
  const d1 = cross(c, d, a)
  const d2 = cross(c, d, b)
  const d3 = cross(a, b, c)
  const d4 = cross(a, b, d)
  return d1 * d2 < 0 && d3 * d4 < 0
}

const TRAIT_KEYS = [
  'line', 'trunk', 'turn', 'branches', 'branchA', 'branchB',
  'stop', 'stopAt', 'ticks', 'tickSide', 'terminus',
] as const

/** The style's own traits, without the background fields DiceBear adds to `extra`. */
function traitsOf(seed: string, line?: number): RoutePlateTraits {
  const extra = createAvatar(routePlate, { seed, ...(line === undefined ? {} : { line }) })
    .toJson().extra
  return Object.fromEntries(TRAIT_KEYS.map((k) => [k, extra[k]])) as unknown as RoutePlateTraits
}

const TRUNK_NAMES = Object.keys(TRUNKS) as TrunkName[]

describe('routePlate palette', () => {
  it('keeps white legible on every line colour', () => {
    for (const hex of ROUTE_LINES) {
      const contrast = 1.05 / (luminance(hex) + 0.05)
      expect(contrast, `${hex} white contrast ${contrast.toFixed(2)}`).toBeGreaterThanOrEqual(3)
      expect(rgbToLab(hex)[0], `${hex} L*`).toBeLessThan(78)
    }
  })

  it('keeps line colours perceptually apart', () => {
    let min = Infinity
    let closest = ''
    for (let i = 0; i < ROUTE_LINES.length; i++) {
      for (let j = i + 1; j < ROUTE_LINES.length; j++) {
        const d = deltaE00(ROUTE_LINES[i], ROUTE_LINES[j])
        if (d < min) {
          min = d
          closest = `${ROUTE_LINES[i]} vs ${ROUTE_LINES[j]}`
        }
      }
    }
    expect(min, `closest pair ${closest} at ${min.toFixed(2)} dE`).toBeGreaterThan(18)
  })

  it('wraps a pinned line index onto the palette, negatives included', () => {
    expect(lineAt(0)).toBe(ROUTE_LINES[0])
    expect(lineAt(ROUTE_LINES.length + 2)).toBe(ROUTE_LINES[2])
    expect(lineAt(-1)).toBe(ROUTE_LINES[ROUTE_LINES.length - 1])
  })
})

describe('routePlate geometry', () => {
  it('keeps every node on its trunk and far enough inside for a full ring', () => {
    for (const name of TRUNK_NAMES) {
      const { path, nodes } = TRUNKS[name]
      for (const { p } of nodes) {
        const onPath = path.slice(1).some((b, i) => {
          const a = path[i]
          const cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
          const within =
            Math.min(a[0], b[0]) <= p[0] && p[0] <= Math.max(a[0], b[0]) &&
            Math.min(a[1], b[1]) <= p[1] && p[1] <= Math.max(a[1], b[1])
          return Math.abs(cross) < 1e-6 && within
        })
        expect(onPath, `${name} node ${p}`).toBe(true)
        for (const v of p) {
          expect(v, `${name} node ${p}`).toBeGreaterThanOrEqual(13)
          expect(v, `${name} node ${p}`).toBeLessThanOrEqual(87)
        }
      }
    }
  })

  it('offers every trunk a choice of branches, none of which cross it', () => {
    for (const name of TRUNK_NAMES) {
      const trunk = TRUNKS[name]
      const cands = branchCandidates(trunk)
      expect(cands.length, name).toBeGreaterThanOrEqual(2)
      for (const { node, dir } of cands) {
        const from = trunk.nodes[node].p
        // Start just off the node: the branch legitimately touches the trunk there.
        const a: P = [from[0] + dir[0] * 2, from[1] + dir[1] * 2]
        const b: P = [from[0] + dir[0] * 150, from[1] + dir[1] * 150]
        for (let i = 1; i < trunk.path.length; i++) {
          expect(crosses(a, b, trunk.path[i - 1], trunk.path[i]), `${name} ${node} ${dir}`).toBe(false)
        }
      }
    }
  })
})

describe('routePlate style', () => {
  it('renders a well-formed SVG plate filled with its line colour', () => {
    const svg = createAvatar(routePlate, { seed: 'junction' }).toString()
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
    expect(doc.querySelector('parsererror')).toBeNull()
    const root = doc.documentElement
    expect(root.nodeName.toLowerCase()).toBe('svg')
    expect(root.getAttribute('viewBox')).toBe('0 0 100 100')
    // The first rect inside the masked group; DiceBear's own corner mask is a rect too.
    const plate = root.querySelector('g > rect')
    expect(plate?.getAttribute('fill')).toBe(traitsOf('junction').line)
    // At least the trunk and the stop marker.
    expect(root.querySelectorAll('path').length).toBeGreaterThanOrEqual(1)
    expect(root.querySelectorAll('circle').length).toBeGreaterThanOrEqual(1)
  })

  it('renders a local data URI with no remix claim in its metadata', () => {
    const svg = createAvatar(routePlate, { seed: 'junction' }).toString()
    // The art is first-party, so DiceBear's "Remix of" rights line must not appear.
    expect(svg).not.toContain('Remix of')
    expect(svg).toContain('Design by')
    expect(createAvatar(routePlate, { seed: 'junction' }).toDataUri()).toMatch(
      /^data:image\/svg\+xml/,
    )
  })

  it('is deterministic and distinct across seeds', () => {
    const a = createAvatar(routePlate, { seed: 'oncall' }).toString()
    expect(createAvatar(routePlate, { seed: 'oncall' }).toString()).toBe(a)
    expect(createAvatar(routePlate, { seed: 'junction' }).toString()).not.toBe(a)
  })

  it('draws through compose, so explicit traits reproduce a seeded plate', () => {
    const traits = traitsOf('oncall')
    expect(createAvatar(routePlate, { seed: 'oncall' }).toString()).toContain(compose(traits))
  })

  it('pins only the colour when a line is given', () => {
    const free = traitsOf('oncall')
    for (let i = 0; i < ROUTE_LINES.length; i++) {
      const pinned = traitsOf('oncall', i)
      expect(pinned.line).toBe(ROUTE_LINES[i])
      // The override is applied after the draw, so every other trait is untouched.
      expect({ ...pinned, line: free.line }).toEqual(free)
    }
  })

  it('pins the draw order', () => {
    // The prng is one positional stream, so these tuples change if a draw is
    // inserted, removed, or reordered in `create` — which would re-roll every
    // existing plate. Appending a NEW trait at the end is safe and leaves these
    // untouched; if this test fails, a draw moved. The values themselves carry no
    // meaning beyond being what the frozen order produces.
    expect(traitsOf('oncall')).toEqual(PINNED.oncall)
    expect(traitsOf('junction')).toEqual(PINNED.junction)
    expect(traitsOf('mochi')).toEqual(PINNED.mochi)
  })

  it('names every value its pick lists can produce', () => {
    // A typo in a pick list would silently render a trunk as the fallback.
    for (let i = 0; i < 400; i++) {
      const t = traitsOf(`seed-${i}`)
      expect(TRUNKS).toHaveProperty(t.trunk)
      expect(ROUTE_LINES).toContain(t.line)
      expect(['ring', 'dot']).toContain(t.stop)
      expect([0, 1, 2]).toContain(t.branches)
      expect([0, 1, 2]).toContain(t.ticks)
      expect([1, -1]).toContain(t.tickSide)
      expect(t.turn).toBeGreaterThanOrEqual(0)
      expect(t.turn).toBeLessThan(8)
    }
  })
})

const PINNED: Record<string, RoutePlateTraits> = {
  oncall: {
    line: '#5b2a86', trunk: 'elbow', turn: 5, branches: 2, branchA: 882, branchB: 963,
    stop: 'ring', stopAt: 56, ticks: 1, tickSide: 1, terminus: false,
  },
  junction: {
    line: '#00808c', trunk: 'crank', turn: 4, branches: 2, branchA: 33, branchB: 851,
    stop: 'ring', stopAt: 631, ticks: 2, tickSide: 1, terminus: false,
  },
  mochi: {
    line: '#00808c', trunk: 'hook', turn: 4, branches: 1, branchA: 756, branchB: 158,
    stop: 'ring', stopAt: 160, ticks: 0, tickSide: -1, terminus: false,
  },
}
