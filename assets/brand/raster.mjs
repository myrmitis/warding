// Rasterize SVG strings to transparent PNGs at exact pixel sizes.
//
// Driven by build.py, which writes a JSON job list: [{ svg, w, h, out }, ...].
// Uses the Playwright copy in website/node_modules so the brand kit needs no
// dependency of its own. Set CHROME to a Chromium binary when Playwright's
// bundled browser is not installed.
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(here, '..', '..', 'website', 'package.json'))
const { chromium } = require('playwright')

const jobs = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined })
const page = await browser.newPage({ deviceScaleFactor: 1 })
for (const job of jobs) {
  await page.setViewportSize({ width: job.w, height: job.h })
  const sized = job.svg.replace('<svg', `<svg width="${job.w}" height="${job.h}" style="display:block"`)
  await page.setContent(`<html><body style="margin:0;background:transparent">${sized}</body></html>`)
  await page.screenshot({
    path: job.out,
    omitBackground: true,
    clip: { x: 0, y: 0, width: job.w, height: job.h },
  })
}
await browser.close()
