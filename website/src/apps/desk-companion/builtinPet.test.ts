import { describe, expect, it } from 'vitest'
import { builtinAnimations, builtinArt } from './builtinPet'

describe('built-in pet gallery', () => {
  it('uses the live pet art for each gallery slot', () => {
    const animations = builtinAnimations()
    expect(Object.keys(animations)).toEqual([
      'idle', 'done', 'error', 'happy', 'sleepy', 'curious', 'busy', 'scared',
    ])
    for (const [slot, animation] of Object.entries(animations)) {
      expect(animation).toEqual({ content: builtinArt(slot), format: 'svg' })
      expect(animation.content).toContain('<svg')
    }
    expect(builtinArt('happy')).toBe(builtinArt('done'))
    expect(builtinArt('loading')).toBe(builtinArt('curious'))
    expect(builtinArt('scared')).toBe(builtinArt('error'))
  })

  it.each([undefined, null, '', 'unknown', 'constructor', '__proto__']) (
    'falls back to the resting drawing for %s', key => {
      expect(builtinArt(key)).toBe(builtinArt('idle'))
    },
  )
})
