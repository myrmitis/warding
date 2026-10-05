/**
 * Cost-class classifier for Settings role pickers.
 *
 * Mirrors `classify_cost` in `src/junction/model_router/routing.py` so the
 * dashboard does not offer an opus id on an economy role. Keep the token sets
 * in lockstep with that module.
 */

export type ModelCostClass = 'economy' | 'standard' | 'capable'

const CHEAP_SIZE = new Set(['flash', 'haiku', 'highspeed', 'free', 'tiny', 'lite', 'nano'])
const CAPABLE_TOKENS = new Set(['opus', 'pro', 'max', 'ultra', 'fable', 'k3', 'sol', 'terra'])
const CAPABLE_LEAVES = new Set(['grok-4.5', 'grok-4.6', 'kimi-k3', 'k3'])
const CAPABLE_FAMILIES = ['gpt-5', 'glm-5', 'grok-4', 'kimi-k3', 'claude-opus'] as const

export function classifyCost(modelId: string): ModelCostClass {
  const raw = (modelId || '').trim().toLowerCase()
  if (!raw) return 'standard'
  const leaf = raw.includes('/') ? raw.slice(raw.lastIndexOf('/') + 1) : raw
  const tokens = new Set(leaf.split(/[^a-z0-9]+/).filter(Boolean))
  if (tokensOverlap(tokens, CHEAP_SIZE) || leaf.endsWith('-free') || leaf.endsWith(':free')) {
    return 'economy'
  }
  if (CAPABLE_LEAVES.has(leaf) || CAPABLE_LEAVES.has(raw) || familyIsCapable(raw, leaf)) {
    return 'capable'
  }
  if (tokensOverlap(tokens, CAPABLE_TOKENS)) return 'capable'
  if (tokens.has('turbo')) return 'economy'
  return 'standard'
}

function familyIsCapable(raw: string, leaf: string): boolean {
  return CAPABLE_FAMILIES.some(family => leaf.startsWith(family) || raw.startsWith(family))
}

function tokensOverlap(left: Set<string>, right: Set<string>): boolean {
  for (const token of left) {
    if (right.has(token)) return true
  }
  return false
}
