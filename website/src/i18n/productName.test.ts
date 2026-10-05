/**
 * The `{{productName}}` contract.
 *
 * Catalog values interpolate the product name instead of hardcoding it,
 * so a downstream edition can rebrand by overriding one variable from its
 * composition root instead of forking every locale file. These tests pin the
 * three properties the arrangement rests on: the stock default renders the
 * exact same English a hardcoded literal would, the variable is wired as an
 * i18next `defaultVariables` (so it survives the planned lazy-catalog
 * migration untouched), and a call-time variable still wins.
 *
 * Manifest-sync `apps.<id>.manifest.*` keys and repo-attribution copy that
 * wrap the upstream GitHub URL stay literal by contract.
 */

import { describe, it, expect } from 'vitest'

import { CATALOGS as RUNTIME_CATALOGS } from './catalogs'
import { initI18n, i18next, setProductName } from './index'

function flatten(obj: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj === null || typeof obj !== 'object') return out
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') {
      Object.assign(out, flatten(value, path))
    } else {
      out[path] = String(value)
    }
  }
  return out
}

/**
 * English passthrough still sitting in every locale. Converting them to
 * `{{productName}}` makes `changed-passthrough` fail: the rest of the
 * sentence is still English. Leave them until they are actually translated.
 */
const PASSTHROUGH_LITERALS = new Set([
  'apps.opsMissionControl.settingsPanel.find_it_at_the_bottom_of_the_channel_s_detail_di',
  'apps.opsMissionControl.settingsPanel.get_a_notification_when_something_changes_that_n',
  'apps.opsMissionControl.settingsPanel.mirror_incidents_to_a_channel_as_a_live_board_on',
  'pages.settings.remoteInstancesPanel.doesnt_manage',
  'pages.settings.remoteInstancesPanel.profile_name_only',
  'pages.settings.remoteInstancesPanel.unverified_cloud_note',
])

/**
 * Repo-attribution copy: each names this project as the target of a link to its
 * GitHub repository, whose URL is hardcoded, so the name stays literal.
 */
const REPO_ATTRIBUTION_KEYS = new Set(['star_junction_on_github'])

function isExempt(key: string): boolean {
  const parts = key.split('.')
  if (parts.includes('manifest')) return true
  if (REPO_ATTRIBUTION_KEYS.has(parts[parts.length - 1])) return true
  if (PASSTHROUGH_LITERALS.has(key)) return true
  return false
}

// No-op — the vitest setup file already initialized i18n. Explicit so this
// file also works standalone, and so the late-override test below is
// self-evidently running against an initialized instance.
initI18n()

// A value shaped exactly like the rewritten catalog strings will be. Injected
// under a test-only key so the assertion is independent of how much of the
// catalog has been converted.
i18next.addResource('en', 'translation', 'test.updating_product', 'Updating {{productName}}…')

describe('productName interpolation variable', () => {
  it('defaults to the stock product name', () => {
    expect(i18next.options.interpolation?.defaultVariables).toMatchObject({
      productName: 'Warding',
    })
  })

  it('renders a placeholder-bearing value identically to the old literal', () => {
    expect(i18next.t('test.updating_product')).toBe('Updating Warding…')
  })

  it('lets a call-time variable win over the default', () => {
    expect(i18next.t('test.updating_product', { productName: 'Acme' })).toBe('Updating Acme…')
  })

  it('keeps the update-restart handoff copy rebrandable', () => {
    const copy = i18next.t('pages.settings.aboutPanel.installing_quiet_note', { productName: 'Acme' })
    expect(copy).toContain('Acme')
    expect(copy).not.toContain('Junction')
  })

  it('does not hardcode the product name outside manifest and attribution keys', () => {
    const en = flatten(
      (RUNTIME_CATALOGS as Record<string, { translation: unknown }>).en.translation,
    )
    const offenders = Object.entries(en)
      .filter(([key, value]) => !isExempt(key) && value.includes('Warding'))
      .map(([key]) => key)
    expect(offenders).toEqual([])
  })

  it('refuses a late override rather than half-applying it', () => {
    // After init the variable has been handed to i18next; silently accepting
    // the call would leave the UI unchanged while the caller believes it
    // rebranded. Vitest runs with import.meta.env.DEV true, so this throws.
    expect(() => setProductName('Acme')).toThrow(/before initI18n/)
  })
})
