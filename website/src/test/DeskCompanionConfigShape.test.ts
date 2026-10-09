/**
 * Config reads and writes go to the routes that serve them.
 *
 * A grep-shaped test is the right instrument here: the bridge is the only place
 * that names the paths, and the bug it guards (a read aimed at a POST-only route)
 * throws nothing and fails no typecheck — the read just comes back empty.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const APP = join(__dirname, '..', 'apps', 'desk-companion')
const read = (f: string) => readFileSync(join(APP, f), 'utf8')

describe('config reads go to an endpoint that answers GET', () => {
  it('custom presets are read from the reminders snapshot, not the POST-only config path', () => {
    const src = read('petBridge.ts')
    // Assert on the CALL, not the surrounding prose: the comment above it names
    // CONFIG_PATH to explain why it is wrong, which a text search would count.
    const call = src.match(/presetsLoadCustom\(\)[\s\S]*?getJson<[^>]*>\((\w+)\)/)
    expect(call?.[1]).toBe('REMINDERS_PATH')
  })

  it('presets are still SAVED to the config path, which is the POST route', () => {
    const src = read('petBridge.ts')
    const saver = src.slice(src.indexOf('async presetsSaveCustom('))
    expect(saver.slice(0, saver.indexOf('},'))).toContain('CONFIG_PATH')
  })
})
