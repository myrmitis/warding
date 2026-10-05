/**
 * The built-in pet: the default cat, compiled into this app's bundle.
 *
 * The art is the dashboard's default pet, `src/assets/pets/`, imported as raw SVG
 * text (Vite `?raw`) — the same art Mochi's `builtinPacks.ts` draws. It lives in the
 * core rather than in either app because Companion and Mochi ship and version
 * separately (see `.jscpd.json`), so neither imports the other. Two reasons it is
 * text rather than a URL: the user's recolour is applied to the markup itself
 * (`applySvgColorMap`), and the gallery's colour customizer and state thumbnails
 * read the same strings, so every surface draws the one cat.
 *
 * The bodies carry their own eyes and their own gentle loop, so the built-in needs
 * no overlay layer: a surface picks the drawing for a state or mood and renders it.
 */
import idleSvg from '../../assets/pets/mochi_idle.svg?raw'
import doneSvg from '../../assets/pets/mochi_done.svg?raw'
import errorSvg from '../../assets/pets/mochi_error.svg?raw'
import sleepingSvg from '../../assets/pets/mochi_sleeping.svg?raw'
import thinkingSvg from '../../assets/pets/mochi_thinking.svg?raw'
import workingSvg from '../../assets/pets/mochi_working.svg?raw'

/**
 * The built-in pack's id. Canonical in the backend (`appearances.py` `DEFAULT_PACK`),
 * so it is a contract: every surface here reads it from this one constant.
 */
export const BUILTIN_PACK = 'default-mochi'

/**
 * Which drawing each key shows. Covers both vocabularies a caller may hold: the
 * pet's display states (`idle` / `loading` / `done` / `error`) and the pack slots
 * and moods the gallery lists. The breathing phases are absent on purpose — the
 * exercise scales the resting body itself.
 */
const ART_FOR_KEY: Record<string, string> = {
  idle: idleSvg,
  loading: thinkingSvg,
  done: doneSvg,
  error: errorSvg,
  happy: doneSvg,
  sleepy: sleepingSvg,
  curious: thinkingSvg,
  busy: workingSvg,
  scared: errorSvg,
}

/** The built-in's SVG for a state or mood key; the resting body for anything else. */
export function builtinArt(key?: string | null): string {
  return (key && Object.prototype.hasOwnProperty.call(ART_FOR_KEY, key) && ART_FOR_KEY[key]) || idleSvg
}

/**
 * The built-in pack's slots in the gallery's detail shape, so its thumbnails, its
 * state grid and the colour customizer read the same art as the live pet.
 */
export function builtinAnimations(): Record<string, { content: string; format: 'svg' }> {
  return Object.fromEntries(
    ['idle', 'done', 'error', 'happy', 'sleepy', 'curious', 'busy', 'scared'].map((slot) => [
      slot,
      { content: builtinArt(slot), format: 'svg' as const },
    ]),
  )
}
