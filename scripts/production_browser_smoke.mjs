// Explicit live acceptance against synthetic records only. No screenshots, traces or payload logs.
import fs from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium, expect } = require('@playwright/test')
const baseURL = process.env.CQA_PROXY_URL
if (new URL(baseURL).protocol !== 'https:') throw new Error('HTTPS required')
const credentialsPath = process.env.CQA_CREDENTIALS_FILE
if (fs.statSync(credentialsPath).mode & 0o077) throw new Error('Private credentials required')
const credentials = JSON.parse(fs.readFileSync(credentialsPath, 'utf8'))
const evaluationId = Number(process.env.CQA_SYNTHETIC_EVALUATION_ID)
if (!Number.isSafeInteger(evaluationId) || evaluationId <= 0) throw new Error('Evaluation ID required')
const checklistId = Number(process.env.CQA_SYNTHETIC_CHECKLIST_ID)
if (!Number.isSafeInteger(checklistId) || checklistId <= 1) throw new Error('Synthetic checklist ID required')
let step = 'connect'
const browser = await chromium.launch({ args: ['--disable-gpu'] })
try {
  const context = await browser.newContext({ baseURL, httpCredentials: credentials,
    viewport: { width: 1440, height: 1000 } })
  const api = async (path) => {
    const response = await context.request.get('/api/' + path)
    if (!response.ok()) throw new Error('API request failed')
    return response.json()
  }
  const before = await api(`evaluations/${evaluationId}`)
  const conversation = await api(`conversations/${before.conversation_id}`)
  const dataset = await api(`datasets/${conversation.dataset_id}`)
  if (!dataset.group_id.startsWith('LOCAL-SMOKE-') || !['test', 'manual'].includes(before.source)) {
    throw new Error('Only explicitly synthetic smoke evaluations allowed')
  }
  const originalChecklist = await api('checklists/1')
  const versions = await api(`checklists/${checklistId}/versions`)
  const originalVersion = versions.find(v => v.id === before.checklist_version_id)
  if (!originalVersion) throw new Error('Synthetic checklist version missing')
  expect(originalVersion.checklist_id).toBe(checklistId)
  const checklist = await api(`checklists/${checklistId}`)
  if (!checklist.name.startsWith('Smoke LOCAL-SMOKE-')) throw new Error('Synthetic checklist required')
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.name))
  const goto = async path => {
    await page.goto('/#' + path)
    await expect(page.locator('main h1')).toBeVisible()
  }
  step = 'routes'
  for (const path of ['/', '/conversations', `/conversations/${conversation.id}`,
    `/evaluations/${evaluationId}`, '/checklists', `/checklists/${checklistId}`,
    '/appeals', '/ai-jobs', '/datasets']) await goto(path)
  step = 'evidence'
  await goto(`/evaluations/${evaluationId}`)
  await expect(page.locator('.criterion-result')).toHaveCount(before.results.length)
  const quote = before.results.flatMap(r => r.evidence).find(e => e.evidence_type === 'quote')
  if (!quote) throw new Error('Synthetic quote required')
  await page.getByRole('button', { name: /Цитата/ }).first().click()
  await expect(page.locator(`#message-${quote.message_id}`)).toHaveClass(/highlighted/)
  await expect(page.locator(`#message-${quote.message_id}`)).toBeInViewport()
  await expect(page.locator('.criterion-result').nth(2)).toContainText('N/A')
  step = 'appeal'
  await page.locator('.criterion-result').nth(5).getByRole('button', { name: 'Оспорить оценку' }).click()
  await page.getByLabel('Причина несогласия').fill('Синтетическая проверка HTTPS интерфейса: пересмотреть управление диалогом.')
  await page.getByRole('button', { name: 'Подать апелляцию' }).click()
  await expect(page).toHaveURL(/appeals\/\d+/)
  const appealId = Number(page.url().split('/').at(-1))
  await page.getByLabel('Решение', { exact: true }).selectOption('revised')
  await page.getByLabel('Новый ответ').selectOption('10')
  await page.getByLabel('Причина решения').fill('Синтетическая проверка сохранения решения через production UI.')
  await page.getByRole('button', { name: 'Сохранить решение' }).click()
  await expect(page.getByRole('heading', { name: 'Решение сохранено' })).toBeVisible()
  const revised = await api(`evaluations/${evaluationId}`)
  expect(revised.initial_score).toBe(before.initial_score)
  expect(revised.final_score).toBe('93.75')
  step = 'checklist'
  await goto(`/checklists/${checklistId}`)
  await page.getByRole('button', { name: 'Создать новую версию' }).click()
  await page.getByLabel('Описание критерия', { exact: true }).first().fill(
    'Оператор в первом ответе поздоровался на языке клиента, представился и сообщил, что разговор записывается. Да только при выполнении всех трёх условий.')
  await page.getByRole('button', { name: 'Сохранить версию', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Создать новую версию' })).toBeVisible()
  await page.getByRole('button', { name: 'Активировать', exact: true }).click()
  await page.getByRole('button', { name: 'Подтвердить', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  const updated = await api(`checklists/${checklistId}`)
  expect(updated.active_version_id).not.toBe(checklist.active_version_id)
  const savedVersions = await api(`checklists/${checklistId}/versions`)
  expect(savedVersions.find(v => v.id === originalVersion.id)).toEqual(originalVersion)
  expect(await api(`evaluations/${evaluationId}`)).toEqual(revised)
  step = 'reevaluation'
  await goto(`/conversations?dataset=${dataset.id}&checklist_id=${checklistId}`)
  await page.getByRole('button', { name: `Оценить ${conversation.conversation_id}`, exact: true }).click()
  await page.getByRole('button', { name: 'Поставить в очередь', exact: true }).click()
  await expect(page).toHaveURL(/ai-jobs\/\d+/)
  const jobId = Number(page.url().split('/').at(-1))
  const job = await api(`ai/jobs/${jobId}`)
  expect(job.checklist_version_id).toBe(updated.active_version_id)
  step = 'json_import'
  const group = 'SYNTHETIC-REHEARSAL-' + Date.now()
  const payload = { error: '', isSuccess: true, data: { dataset_group_id: group,
    total_records: 1, records: [{ conversation_id: 'synthetic-rehearsal-ru',
      language: 'RU', channel: 'agent chat', audio_url: null, transcript: [
        { timestamp: '00:00', speaker: 'client', text: 'Здравствуйте! Можно говорить на русском?' },
        { timestamp: '00:01', speaker: 'operator', text: 'Здравствуйте! Я Анна. Да, можем говорить на русском.' },
        { timestamp: '00:02', speaker: 'client', text: 'Спасибо, это всё.' },
        { timestamp: '00:03', speaker: 'operator', text: 'Если понадобится помощь, обращайтесь. До свидания!' },
      ] }] } }
  payload.data.records.push({ ...payload.data.records[0], conversation_id: 'synthetic-rehearsal-ru-2' })
  payload.data.total_records = payload.data.records.length
  await goto('/datasets')
  await page.getByLabel('JSON-файл набора', { exact: false }).setInputFiles({
    name: 'synthetic-rehearsal.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(payload)) })
  await page.getByRole('button', { name: 'Загрузить JSON', exact: true }).click()
  await expect(page.getByRole('heading', { name: `Набор ${group} импортирован` })).toBeVisible()
  await expect(page.locator('.import-result')).toContainText('Добавлено 2')
  await page.getByRole('button', { name: 'Загрузить JSON', exact: true }).click()
  await expect(page.locator('.import-result')).toContainText('Пропущено 2')
  step = 'batch'
  await page.getByRole('link', { name: 'Открыть набор и запустить batch' }).click()
  await page.getByRole('button', { name: 'Выбрать все найденные (2)' }).click()
  await page.getByRole('button', { name: 'Оценить выбранные (2)' }).click()
  await page.getByRole('button', { name: 'Поставить в очередь', exact: true }).click()
  await expect(page).toHaveURL(/ai-batches\/\d+/)
  const batchId = Number(page.url().split('/').at(-1))
  expect((await api(`ai/batches/${batchId}`)).total).toBe(2)
  step = 'responsive'
  for (const width of [1440, 1280, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const path of [`/conversations/${conversation.id}`, `/evaluations/${evaluationId}`,
      `/checklists/${checklistId}`, `/appeals/${appealId}`, `/ai-jobs/${jobId}`, `/ai-batches/${batchId}`, '/datasets']) {
      await goto(path)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  }
  expect(await api('checklists/1')).toEqual(originalChecklist)
  expect(errors).toEqual([])
  console.log(JSON.stringify({ status: 'passed', protected_https: true, routes: 9,
    evidence: true, appeal_id: appealId, initial_score: revised.initial_score,
    final_score: revised.final_score, checklist_version_id: updated.active_version_id,
    job_id: jobId, batch_id: batchId, json_import_idempotent: true,
    widths: [1440, 1280, 768, 390], page_errors: 0, writes: 'synthetic_only' }))
} catch (error) {
  console.error(JSON.stringify({ status: 'failed', step, category: error.name }))
  process.exitCode = 1
} finally {
  await browser.close()
}
