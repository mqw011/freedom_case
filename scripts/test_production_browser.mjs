// Local synthetic production-build smoke. Never capture real client data.
import fs from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium, expect } = require('@playwright/test')
const baseURL = process.env.CQA_PROXY_URL
if (new URL(baseURL).hostname !== '127.0.0.1') throw new Error('Local synthetic test only')
const credentials = JSON.parse(fs.readFileSync(process.env.CQA_CREDENTIALS_FILE, 'utf8'))
const browser = await chromium.launch({ args: ['--disable-gpu'] })
try {
  const context = await browser.newContext({
    baseURL, httpCredentials: credentials, ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 },
  })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.name))
  for (const path of ['/', '/conversations', '/conversations/1', '/evaluations/1',
    '/checklists', '/checklists/1', '/appeals', '/ai-jobs', '/ai-jobs/1', '/datasets']) {
    await page.goto('/#' + path)
    await expect(page.locator('main h1')).toBeVisible()
  }
  await page.goto('/#/evaluations/1')
  await expect(page.locator('.criterion-result')).toHaveCount(8)
  await page.getByRole('button', { name: /Цитата/ }).first().click()
  await expect(page.locator('#message-4')).toHaveClass(/highlighted/)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/conversations/1')
  await expect(page.locator('.message')).toHaveCount(115)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.goto('/docs')
  await expect(page.getByRole('heading', { name: /Freedom Broker CQA/ })).toContainText('Freedom Broker CQA', { timeout: 30000 })
  expect(errors).toEqual([])
  console.log(JSON.stringify({ browser: 'passed', routes: 10, evidence: 'passed',
    mobile: 'passed', swagger: 'passed', pageErrors: 0, data: 'synthetic' }))
} finally {
  await browser.close()
}
