import { describe, expect, it } from 'vitest'
import { classifyCost } from './modelCostClass'

describe('classifyCost', () => {
  it('treats size tokens as economy and flagship families as capable', () => {
    expect(classifyCost('deepseek/deepseek-v4-flash')).toBe('economy')
    expect(classifyCost('claude-haiku-4.5')).toBe('economy')
    expect(classifyCost('llama-3-turbo')).toBe('economy')
    expect(classifyCost('kimi-oauth/k3')).toBe('capable')
    expect(classifyCost('glm-5-turbo')).toBe('capable')
    expect(classifyCost('gpt-5.4')).toBe('capable')
    expect(classifyCost('claude-opus-4.8')).toBe('capable')
    expect(classifyCost('minimax-m3')).toBe('standard')
    expect(classifyCost('claude-sonnet-4')).toBe('standard')
  })
})
