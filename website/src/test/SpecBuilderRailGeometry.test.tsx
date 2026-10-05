// Spec Builder rail geometry: the persisted width/collapsed state that the
// shared useColumnResize hook reads on mount.
import { describe, it, expect, beforeEach } from 'vitest'
import {
  LS, loadRailWidth, loadRailCollapsed,
  DEFAULT_RAIL_WIDTH, MIN_RAIL_WIDTH, MAX_RAIL_WIDTH,
} from '../apps/spec-builder/api'

describe('loadRailWidth', () => {
  beforeEach(() => localStorage.clear())

  it('returns the stored width when it is in range', () => {
    localStorage.setItem(LS.railWidth, '300')
    expect(loadRailWidth()).toBe(300)
  })

  it('falls back to the default for a missing, junk or out-of-range value', () => {
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
    for (const bad of ['', 'wide', String(MIN_RAIL_WIDTH - 1), String(MAX_RAIL_WIDTH + 1)]) {
      localStorage.setItem(LS.railWidth, bad)
      expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
    }
  })
})

describe('loadRailCollapsed', () => {
  beforeEach(() => localStorage.clear())

  it('reads the current key, where 1 means collapsed', () => {
    localStorage.setItem(LS.railCollapsed, '1')
    expect(loadRailCollapsed()).toBe(true)
    localStorage.setItem(LS.railCollapsed, '0')
    expect(loadRailCollapsed()).toBe(false)
  })

  it('defaults to expanded with nothing stored', () => {
    expect(loadRailCollapsed()).toBe(false)
  })
})
