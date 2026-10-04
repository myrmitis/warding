/**
 * Screenshot harness for Issue Radar → Stewards.
 *
 * Runs the REAL built SPA (website/dist) behind the shared in-process static
 * server, with every /api/** answered from fixtures — so it needs no gateway, no
 * kiro-cli, no GitHub credential and no real repository. That matters here more
 * than usual: a steward's state (claims, work log) only exists after a worker has run
 * for hours, so fixtures are the only way to photograph a populated board at all.
 *
 * Fixtures live in lib/issue-radar-stewards-fixtures.mjs, shared with
 * record-stewards.mjs — a copy in each script is a jscpd clone finding.
 *
 * Usage: node scripts/capture-stewards.mjs [outDir]
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { serveDist } from './lib/serve-dist.mjs'
import { logPageProblems, stubDashboardApi, json } from './lib/stub-dashboard-api.mjs'
import { makeExtra, seedState, OWNER, REPO } from './lib/issue-radar-stewards-fixtures.mjs'

const OUT = process.argv[2] || '../temp-screenshots/stewards'
mkdirSync(OUT, { recursive: true })

const extra = makeExtra(json)

/** The stewards surface's own always-present control, and the default readiness
 *  locator. Addressed by testid, never by copy: this harness used to wait on the
 *  words "Your Desk" and broke the moment that label was renamed — then broke
 *  again when the view was removed. */
const STEWARD_READY = '[data-testid="steward-create"]'

async function main() {
  const { srv, base } = await serveDist()
  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1540, height: 1000 },
    // 11-13px UI type renders soft at 1x, which reads as a rendering bug in a
    // screenshot rather than as the anti-aliasing it is.
    deviceScaleFactor: 2,
  })

  let page = null

  /** Fresh page per theme — stubDashboardApi bakes the theme into /api/theme/boot. */
  async function load(theme, stewardUi, ui, ready) {
    if (page) await page.close()
    page = await context.newPage()
    logPageProblems(page)
    await stubDashboardApi(page, { theme, extra })
    await page.addInitScript((entries) => {
      for (const [k, v] of Object.entries(entries)) localStorage.setItem(k, v)
    }, seedState(stewardUi, ui))
    await page.goto(`${base}/issue-radar`, { waitUntil: 'domcontentloaded' })
    // Wait on a REAL locator — a blank page must fail loudly, not silently
    // produce an empty screenshot.
    await page.locator(ready ?? STEWARD_READY).first()
      .waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForTimeout(600)
  }

  for (const theme of ['dark', 'light']) {
    await load(theme, { stewardView: { kind: 'steward', id: 'c_7f3a01' }, stewardFilter: 'all' })
    await page.screenshot({ path: join(OUT, `01-steward-page-${theme}.png`) })
    console.log('wrote', `01-steward-page-${theme}.png`)

    // The create dialog, opened through the real control rather than by setting
    // state, so the shot proves the control reaches it.
    await load(theme, { stewardView: { kind: 'steward', id: 'c_7f3a01' }, stewardFilter: 'all' })
    await page.locator(STEWARD_READY).first().click()
    await page.getByRole('dialog').waitFor({ state: 'visible', timeout: 10000 })
    await page.waitForTimeout(500)
    await page.screenshot({ path: join(OUT, `02-new-steward-${theme}.png`) })
    console.log('wrote', `02-new-steward-${theme}.png`)

    // The dialog body scrolls; the limits + workspace sections are below the fold.
    await page.evaluate(() => {
      const scroller = [...document.querySelectorAll('[role="dialog"] *')]
        .find((el) => el.scrollHeight > el.clientHeight + 40)
      if (scroller) scroller.scrollTop = scroller.scrollHeight
    })
    await page.waitForTimeout(400)
    await page.screenshot({ path: join(OUT, `03-new-steward-lower-${theme}.png`) })
    console.log('wrote', `03-new-steward-lower-${theme}.png`)

    // 04 — the steward PROTOCOL settings, which live on the repo settings page
    // because they are repo-wide rather than per-steward.
    await load(theme, { stewardView: { kind: 'steward', id: 'c_7f3a01' }, stewardFilter: 'all' },
      { mainView: 'settings', settingsTarget: { kind: 'repo', owner: OWNER, repo: REPO } },
      '[data-testid="steward-desk-protocol"]')
    const protocol = page.locator('[data-testid="steward-desk-protocol"]').first()
    await protocol.scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await page.screenshot({ path: join(OUT, `04-steward-protocol-settings-${theme}.png`) })
    console.log('wrote', `04-steward-protocol-settings-${theme}.png`)
  }

  await browser.close()
  srv.close()
  console.log('done ->', OUT)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
