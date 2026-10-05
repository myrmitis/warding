/**
 * Body-motion selection, tested at the pure-function layer (like the walk geometry)
 * so the React shell around it does not have to be simulated.
 *
 * These pin the precedence the desktop app shipped in PetWidget's `activeAnim` chain
 * — error > celebrate > curious > fly — and that every motion has a keyframe, so a
 * travelling companion floats and a curious one moves its body rather than looking
 * inert.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { activeAnimFor, animClassFor } from '../apps/desk-companion/petAnim'

const CSS = readFileSync(
  resolve(__dirname, '../apps/desk-companion/petMotion.css'),
  'utf8',
)

describe('activeAnimFor — precedence', () => {
  it('holds still when idle and settled', () => {
    expect(activeAnimFor({ state: 'idle' })).toBeNull()
  })

  it('floats while travelling — the motion an idle hop needs', () => {
    expect(activeAnimFor({ state: 'idle', walking: true })).toBe('fly')
  })

  it('cocks its head when curious, even mid-travel', () => {
    // The expression is the more informative of the two, so it outranks the float.
    expect(activeAnimFor({ state: 'idle', mood: 'curious', walking: true })).toBe('curious')
  })

  it('celebrates a finished job over being curious', () => {
    expect(activeAnimFor({ state: 'done', mood: 'curious' })).toBe('celebrate')
  })

  it('shakes on error above everything else', () => {
    expect(activeAnimFor({ state: 'error', mood: 'curious', walking: true })).toBe('error')
  })

  it('ponders while busy, but never over a ported reaction', () => {
    expect(activeAnimFor({ state: 'loading' })).toBe('ponder-loop')
    expect(activeAnimFor({ state: 'loading', mood: 'curious' })).toBe('curious')
  })

  it('goes quiet when docked — except for a celebration', () => {
    // A half-off-screen body must not be shaken or cocked around; finishing a job is
    // still worth a hop.
    expect(activeAnimFor({ state: 'error', docked: true })).toBeNull()
    expect(activeAnimFor({ state: 'idle', mood: 'curious', docked: true })).toBeNull()
    expect(activeAnimFor({ state: 'idle', walking: true, docked: true })).toBeNull()
    expect(activeAnimFor({ state: 'loading', docked: true })).toBeNull()
    expect(activeAnimFor({ state: 'done', docked: true })).toBe('celebrate')
  })

  it('stays out of the way during breathing', () => {
    // The breathing overlay drives the scale; a second animation would fight it.
    for (const state of ['inhale', 'hold', 'exhale']) {
      expect(activeAnimFor({ state })).toBeNull()
    }
  })
})

describe('animClassFor', () => {
  it('maps a motion to its stylesheet class, and stillness to nothing', () => {
    expect(animClassFor('fly')).toBe('pet-anim-fly')
    expect(animClassFor('ponder-loop')).toBe('pet-anim-ponder-loop')
    expect(animClassFor(null)).toBeUndefined()
  })

  it('every motion it can name has real keyframes to play', () => {
    // A class with no keyframes is a silent no-op — exactly the failure that left the
    // companion inert, so it is pinned here rather than discovered on screen.
    for (const anim of ['error', 'celebrate', 'curious', 'fly', 'look', 'ponder-loop'] as const) {
      expect(CSS, anim).toContain(`.${animClassFor(anim)} `)
    }
    for (const frames of ['pet-error', 'pet-celebrate', 'pet-curious', 'pet-fly', 'pet-look', 'pet-ponder']) {
      expect(CSS, frames).toContain(`@keyframes ${frames} `)
    }
  })

  it('honours reduced motion for the newly ported reactions', () => {
    const reduced = CSS.slice(CSS.indexOf('.pet-anim-look'))
    expect(reduced).toMatch(/prefers-reduced-motion/)
  })
})
