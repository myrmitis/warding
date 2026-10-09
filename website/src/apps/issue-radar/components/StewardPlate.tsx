/**
 * StewardPlate — a steward's identity avatar: the dashboard's route plate
 * (`components/AgentAvatar`), with the line colour chosen per steward.
 *
 * The seed draws the route diagram, so a steward keeps its plate for its whole life.
 * The steward editor's face strip picks the LINE COLOUR: `variant` pins one of
 * `stewardPlateVariantCount` colours over that same diagram, and when it is null the
 * colour is derived from the seed by `djb2`, which is also what the strip marks as
 * the unpinned choice — so the two can never disagree about which face is in use.
 */
import AgentAvatar from '../../../components/AgentAvatar'
import { ROUTE_LINES } from '../../../lib/routePlateAvatar'

/** How many faces the editor offers: one per line colour. Exported so callers
 *  (the face strip, its tests) never hard-code the palette size. */
export const stewardPlateVariantCount = ROUTE_LINES.length

/**
 * Stable non-crypto string hash (djb2) — the same function as `gradientFor` in
 * `components/appstore/gradient.ts` and `pickAnimal` in
 * `pages/scenes/WateringHoleScene.tsx`. Exported so other steward views select
 * per-identity art from the same number instead of writing another copy that
 * could disagree.
 */
export function djb2(s: string): number {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0
  return h
}

/**
 * The face in effect: the pinned `variant` when there is one, else the one the seed
 * hashes to.
 *
 * Hashed from the steward's stable seed rather than taken from roster position, so
 * sorting, pausing or adding a steward never repaints another steward's plate. A pinned
 * value is wrapped, negatives folded, so an out-of-range number stored by an older
 * editor still lands on a real colour.
 */
export function stewardPlateVariant(seed: string, variant?: number | null): number {
  const n = stewardPlateVariantCount
  if (variant != null && Number.isFinite(variant)) return ((Math.trunc(variant) % n) + n) % n
  return djb2(seed) % n
}

export interface StewardPlateProps {
  /** Stable per-steward identity (the avatar seed — NOT its display name, which can be
   *  renamed). Draws the route and, when `variant` is null, the colour. */
  seed: string
  /** Rendered edge length in CSS pixels. */
  size?: number
  /** Pins one of the `stewardPlateVariantCount` faces. `null` (the default) means
   *  "derive from the seed". */
  variant?: number | null
  className?: string
}

export default function StewardPlate({ seed, size = 34, variant = null, className = '' }: StewardPlateProps) {
  return (
    <AgentAvatar
      seed={seed}
      line={stewardPlateVariant(seed, variant)}
      size={size}
      className={className}
    />
  )
}
