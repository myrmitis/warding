/**
 * Deterministic avatar for an agent or an Issue Radar steward.
 *
 * The seed is the name, so an agent keeps the same plate forever and two
 * people looking at the same config see the same roster. Generation is fully
 * LOCAL — `@dicebear/core` renders the SVG in-process from the `routePlate` style
 * definition. Nothing is fetched, so this works offline and no agent name ever
 * leaves the machine (DiceBear's HTTP API is deliberately not used).
 *
 * Rendered as an `<img>` carrying a data URI rather than inlined SVG markup.
 * Two reasons, both load-bearing:
 *  - no `dangerouslySetInnerHTML`, so this stays clear of the frontend-security
 *    rule and there is no HTML-string path to audit;
 *  - inline DiceBear SVGs collide on their internal `id`s when several are on
 *    one page (the corner mask resolves to whichever came first). A data URI is
 *    its own document, so the problem cannot arise and `randomizeIds` is
 *    unnecessary.
 *
 * Swapping the art set is a one-line change to STYLE below; nothing outside
 * this file knows which style is in use.
 */
import { useMemo } from 'react'
import { createAvatar } from '@dicebear/core'
import { routePlate } from '../lib/routePlateAvatar'

/** Transit-signage route plates. See `lib/routePlateAvatar.ts`. */
const STYLE = routePlate

/**
 * Generated data URIs, keyed by seed and pinned line. Module-level rather than
 * per-component so an avatar is generated once per session even though it is
 * rendered in both the roster card and the editor panel.
 */
const CACHE = new Map<string, string>()

export interface AgentAvatarProps {
  /** Agent name — the whole identity of the image. */
  seed: string
  /**
   * Pins the plate's line colour to one palette entry (wrapped), keeping the route
   * the seed draws. Null or absent lets the seed choose the colour too.
   */
  line?: number | null
  /** Rendered edge length in px. */
  size?: number
  className?: string
}

export default function AgentAvatar({ seed, line = null, size = 40, className = '' }: AgentAvatarProps) {
  const src = useMemo(() => {
    const key = JSON.stringify([line, seed])
    const hit = CACHE.get(key)
    if (hit) return hit
    // The plate colour is part of the style rather than a `backgroundColor` list,
    // so that it is drawn from the same seeded stream as every other trait.
    const uri = createAvatar(STYLE, { seed, radius: 12, line }).toDataUri()
    CACHE.set(key, uri)
    return uri
  }, [seed, line])

  return (
    <img
      src={src}
      // Decorative: the agent name is always rendered as text next to it, so
      // announcing the avatar too would just repeat it.
      alt=""
      aria-hidden="true"
      draggable={false}
      width={size}
      height={size}
      style={{ width: size, height: size }}
      className={`shrink-0 rounded-md border border-border bg-bg-elevated ${className}`}
    />
  )
}
