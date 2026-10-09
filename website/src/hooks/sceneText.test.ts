import { describe, expect, it, vi } from 'vitest'
import { drawLabel, drawSpeechBubble, initTextCanvas, sceneLineHeight } from './sceneText'

function context() {
  return {
    measureText: vi.fn((text: string) => ({ width: text.length * 10 })),
    fillText: vi.fn(), fillRect: vi.fn(), save: vi.fn(), restore: vi.fn(),
    beginPath: vi.fn(), roundRect: vi.fn(), fill: vi.fn(), moveTo: vi.fn(),
    lineTo: vi.fn(), closePath: vi.fn(), scale: vi.fn(),
    font: '', fillStyle: '', textAlign: 'start', textBaseline: 'alphabetic',
    globalAlpha: 1, imageSmoothingEnabled: false,
  }
}

describe('scene text rendering', () => {
  it('wraps long words and aligns each label background with its text', () => {
    const ctx = context()
    const count = drawLabel(ctx as unknown as CanvasRenderingContext2D, 'abcdef gh', 100, 20, {
      role: 'detail', color: 'ink', bgColor: 'paper', align: 'end', scale: 2, maxWidth: 30,
    })
    expect(count).toBe(3)
    expect(ctx.fillText.mock.calls).toEqual([
      ['abc', 100, 20], ['def', 100, 20 + sceneLineHeight('detail')],
      ['gh', 100, 20 + 2 * sceneLineHeight('detail')],
    ])
    expect(ctx.fillRect.mock.calls.map(args => args[0])).toEqual([64, 64, 74])
    expect(ctx.textAlign).toBe('start')
    expect(ctx.textBaseline).toBe('alphabetic')
  })

  it('clamps a normalized speech bubble and restores the canvas after drawing', () => {
    const ctx = context()
    drawSpeechBubble(ctx as unknown as CanvasRenderingContext2D, '  abc   def\n ghi jkl ', 50, 100, {
      scale: 1, maxWidth: 30, maxLines: 2, alpha: 0.5,
    })
    expect(ctx.fillText.mock.calls.map(args => args[0])).toEqual(['abc', 'd…'])
    expect(ctx.save).toHaveBeenCalledOnce()
    expect(ctx.restore).toHaveBeenCalledOnce()
    expect(ctx.globalAlpha).toBe(0.5)
    expect(ctx.roundRect.mock.calls[0][2]).toBe(38)
    expect(ctx.lineTo).toHaveBeenCalledTimes(2)
    expect(ctx.textAlign).toBe('start')
    expect(ctx.textBaseline).toBe('alphabetic')
  })

  it('does not draw an empty message and refuses a canvas with no 2D context', () => {
    const ctx = context()
    drawSpeechBubble(ctx as unknown as CanvasRenderingContext2D, ' \n ', 0, 0, { scale: 1 })
    expect(ctx.fillText).not.toHaveBeenCalled()
    const canvas = { getContext: () => null } as unknown as HTMLCanvasElement
    expect(() => initTextCanvas(canvas, 100, 50, 2)).toThrow('Failed to get 2d context')
  })
})
