import AxeBuilder from '@axe-core/playwright'
import { test, expect } from '@playwright/test'
const api = 'http://127.0.0.1:8011/api'
const goto = async (page, path) => {
  await page.goto(`/#${path}`)
  await expect(page.locator('main h1')).toBeVisible()
}
const noOverflow = async (page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
let appealId

test.describe.serial('Real API workflows on isolated synthetic SQLite', () => {
  test('Dashboard aggregates all 65, uses latest final scores and navigates', async ({ page }) => {
    await goto(page, '/')
    await expect(
      page.locator('.kpi').filter({ hasText: 'Всего диалогов' }).locator('strong'),
    ).toHaveText('65')
    await expect(
      page.locator('.kpi').filter({ hasText: 'Оценено диалогов' }).locator('strong'),
    ).toHaveText('2')
    await expect(
      page.locator('.kpi').filter({ hasText: 'Средний балл' }).locator('strong'),
    ).toHaveText('90,94')
    await expect(page.getByLabel('Состояние сервисов').last()).toContainText(
      'LLM provider Недоступен',
    )
    await page.getByRole('link', { name: 'Открыть диалоги', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Диалоги', exact: true })).toBeVisible()
  })
  test('Global filters, pagination, RU KZ EN and chat/voice', async ({ page }) => {
    await goto(page, '/conversations')
    await expect(page.getByText('65 диалогов · фильтры по всему набору')).toBeVisible()
    for (const [language, count] of [
      ['RU', 22],
      ['KZ', 22],
      ['EN', 21],
    ]) {
      await page.getByLabel('Язык', { exact: true }).selectOption(language)
      await expect(page.getByText(`${count} диалогов · фильтры по всему набору`)).toBeVisible()
    }
    await page.getByLabel('Язык', { exact: true }).selectOption('')
    await page.getByLabel('Канал', { exact: true }).selectOption('voice call')
    await expect(page.getByText('5 диалогов · фильтры по всему набору')).toBeVisible()
    await page.getByLabel('Канал', { exact: true }).selectOption('agent chat')
    await expect(page.getByText('60 диалогов · фильтры по всему набору')).toBeVisible()
    await page.getByRole('button', { name: 'Сбросить', exact: true }).click()
    for (let i = 0; i < 4; i++)
      await page.getByRole('button', { name: 'Следующая страница' }).click()
    await expect(page.getByRole('link', { name: 'SYNTHETIC-UI-065', exact: true })).toBeVisible()
    await page.getByLabel('Поиск ID').fill('065')
    await expect(page.getByText('1 диалогов · фильтры по всему набору')).toBeVisible()
    await page.getByRole('link', { name: 'SYNTHETIC-UI-065', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Транскрипт', exact: true })).toBeVisible()
    await page.goBack()
    await expect(page.getByLabel('Поиск ID')).toHaveValue('065')
  })
  test('Evidence quote, range and absence scroll/highlight real IDs in 115 messages', async ({
    page,
  }) => {
    await goto(page, '/evaluations/1')
    await expect(page.locator('.criterion-result')).toHaveCount(8)
    await expect(page.locator('.message')).toHaveCount(115)
    await page
      .getByRole('button', { name: /Цитата/ })
      .first()
      .click()
    await expect(page.locator('#message-4')).toHaveClass(/highlighted/)
    await expect(page.locator('#message-4 mark')).toHaveText(
      'Здравствуйте! Я Анна. Это синтетический пример.',
    )
    await expect(page.locator('#message-4')).toBeFocused()
    await page.getByRole('button', { name: /Диапазон/ }).click()
    await expect(page.locator('.message.highlighted')).toHaveCount(3)
    await page
      .getByRole('button', { name: /Отсутствующее действие/ })
      .first()
      .click()
    await expect(page.locator('#message-114')).toHaveClass(/highlighted/)
    await expect(page.locator('#message-114')).toBeInViewport()
    await expect(page.locator('.evaluation-summary')).toContainText('81,88')
    await expect(page.locator('.criterion-result').nth(2)).toContainText('N/A')
  })
  test('Checklist immutable version edit, activate, job pins new version', async ({
    page,
    request,
  }) => {
    const before = await (await request.get(`${api}/evaluations/1`)).json()
    const old = await (await request.get(`${api}/checklists/1/versions`)).json()
    await goto(page, '/checklists/1')
    await page.getByRole('button', { name: 'Создать новую версию' }).click()
    await page.getByLabel('Название', { exact: true }).first().fill('Контакт — UI revision')
    await page.getByLabel('Вес', { exact: true }).first().fill('11')
    await expect(page.getByText('Total Weight: 101 / 100', { exact: true })).toBeVisible()
    await page.getByLabel('Вес', { exact: true }).nth(1).fill('14')
    await page.getByRole('button', { name: 'Сохранить версию', exact: true }).click()
    await expect(page.getByText('Контакт — UI revision', { exact: false }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Активировать', exact: true }).click()
    await page.getByRole('button', { name: 'Подтвердить', exact: true }).click()
    await expect(page.getByLabel('История версий')).toContainText('Активна')
    const checklist = await (await request.get(`${api}/checklists/1`)).json()
    expect(checklist.active_version_id).toBe(2)
    expect((await (await request.get(`${api}/checklists/1/versions`)).json())[0]).toEqual(old[0])
    expect(await (await request.get(`${api}/evaluations/1`)).json()).toEqual(before)
    await page.getByRole('link', { name: /Выбрать диалоги для переоценки/ }).click()
    await page.getByRole('button', { name: 'Оценить SYNTHETIC-UI-001', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('AI Worker offline')
    await page.getByRole('button', { name: 'Поставить в очередь', exact: true }).click()
    await expect(page).toHaveURL(/ai-jobs\/\d+/)
    await expect(page.locator('main')).toContainText('В очереди')
    const id = page.url().split('/').at(-1)
    expect((await (await request.get(`${api}/ai/jobs/${id}`)).json()).checklist_version_id).toBe(2)
  })
  test('Appeal create and reviewer decision preserve initial 81.88, final becomes 88.13', async ({
    page,
    request,
  }) => {
    await goto(page, '/evaluations/1')
    await page
      .locator('.criterion-result')
      .nth(6)
      .getByRole('button', { name: 'Оспорить оценку' })
      .click()
    await page
      .getByLabel('Причина несогласия')
      .fill('Учебный сценарий: прошу пересмотреть завершение.')
    await page.getByRole('button', { name: 'Подать апелляцию' }).click()
    await expect(page).toHaveURL(/appeals\/\d+/)
    appealId = Number(page.url().split('/').at(-1))
    await page.getByLabel('Решение', { exact: true }).selectOption('revised')
    await page.getByLabel('Новый ответ').selectOption('yes')
    await page
      .getByLabel('Причина решения')
      .fill('Ручной тест пересчёта по подтверждённому завершению.')
    await page.getByRole('button', { name: 'Сохранить решение' }).click()
    await expect(page.getByRole('heading', { name: 'Решение сохранено' })).toBeVisible()
    await expect(page.locator('.evaluation-summary')).toContainText('88,13')
    await expect(page.locator('.evaluation-summary')).toContainText('81,88')
    const e = await (await request.get(`${api}/evaluations/1`)).json()
    expect(e.initial_score).toBe('81.88')
    expect(e.final_score).toBe('88.13')
    expect(e.results[6].answer).toBe('no')
    expect(e.results[6].current_answer).toBe('yes')
    await goto(page, '/evaluations/1')
    await page
      .locator('.criterion-result')
      .nth(2)
      .getByRole('button', { name: 'Оспорить оценку' })
      .click()
    await page.getByLabel('Причина несогласия').fill('Учебная проверка подтверждения N/A')
    await page.getByRole('button', { name: 'Подать апелляцию' }).click()
    await page.getByLabel('Причина решения').fill('N/A подтверждено по контексту')
    await page.getByRole('button', { name: 'Сохранить решение' }).click()
    await expect(page.getByRole('heading', { name: 'Решение сохранено' })).toBeVisible()
    expect((await (await request.get(`${api}/evaluations/1`)).json()).final_score).toBe('88.13')
    await goto(page, '/')
    await expect(
      page.locator('.kpi').filter({ hasText: 'Средний балл' }).locator('strong'),
    ).toHaveText('94,07')
  })
  test('Queued cancel, failed retry and retained attempts use real backend', async ({
    page,
    request,
  }) => {
    await goto(page, '/ai-jobs/1')
    await page.getByRole('button', { name: 'Отменить задание' }).click()
    await page.getByRole('button', { name: 'Подтвердить', exact: true }).click()
    await expect(page.locator('main .badge').first()).toHaveText('Отменено')
    expect((await (await request.get(`${api}/ai/jobs/1`)).json()).status).toBe('cancelled')
    await goto(page, '/ai-jobs/2')
    await expect(page.getByRole('table')).toContainText('synthetic_test_failure')
    await page.getByRole('button', { name: 'Повторить', exact: true }).click()
    await page.getByRole('button', { name: 'Подтвердить', exact: true }).click()
    await expect(page.locator('main .badge').first()).toHaveText('В очереди')
    const job = await (await request.get(`${api}/ai/jobs/2`)).json()
    expect(job.status).toBe('queued')
    expect(job.attempts).toBe(1)
    expect(job.evaluation_id).toBeNull()
  })
  test('Batch all 65 queue and real progress, no successful AI evaluation invented', async ({
    page,
    request,
  }) => {
    await goto(page, '/conversations')
    await page.getByRole('button', { name: 'Выбрать все найденные (65)' }).click()
    await page.getByRole('button', { name: 'Оценить выбранные (65)' }).click()
    await expect(page.getByRole('dialog')).toContainText('Выбрано диалогов: 65')
    await page.getByRole('button', { name: 'Поставить в очередь', exact: true }).click()
    await expect(page).toHaveURL(/ai-batches\/\d+/)
    const id = page.url().split('/').at(-1)
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
    const batch = await (await request.get(`${api}/ai/batches/${id}`)).json()
    expect(batch.total).toBe(65)
    expect(batch.queued).toBe(65)
    expect(batch.completed).toBe(0)
    expect((await (await request.get(`${api}/evaluations?source=ai`)).json()).total).toBe(0)
    await expect(page.getByLabel('Пагинация')).toContainText('страница 1 из 5')
  })
  test('Organizer import, idempotent repeat and JSON import with actual reports', async ({
    page,
    request,
  }) => {
    await goto(page, '/datasets')
    await page.getByLabel('Group ID', { exact: false }).fill('CONTROL-UI')
    await page.getByRole('button', { name: 'Импортировать по group_id' }).click()
    await expect(page.getByRole('heading', { name: 'Набор CONTROL-UI импортирован' })).toBeVisible()
    await expect(page.locator('.import-result')).toContainText('Добавлено 2')
    await page.getByRole('button', { name: 'Импортировать по group_id' }).click()
    await expect(page.locator('.import-result')).toContainText('Пропущено 2')
    const payload = {
      error: '',
      isSuccess: true,
      data: {
        dataset_group_id: 'JSON-UI',
        total_records: 1,
        records: [
          {
            conversation_id: 'synthetic-json-only',
            channel: 'agent chat',
            language: 'KZ',
            audio_url: null,
            transcript: [
              {
                timestamp: '00:01',
                speaker: 'operator',
                text: 'Сәлеметсіз бе! Тест.',
              },
            ],
          },
        ],
      },
    }
    await page.getByLabel('JSON-файл набора', { exact: false }).setInputFiles({
      name: 'synthetic.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(payload)),
    })
    await page.getByRole('button', { name: 'Загрузить JSON', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Набор JSON-UI импортирован' })).toBeVisible()
    await page.getByLabel('Group ID', { exact: false }).fill('FAIL-UI')
    await page.getByRole('button', { name: 'Импортировать по group_id' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    expect((await (await request.get(`${api}/conversations`)).json()).total).toBe(68)
  })
  test('Voice audio fallback, historical content with unavailable provider', async ({ page }) => {
    await goto(page, '/conversations/13')
    await expect(page.locator('audio')).toHaveAttribute('preload', 'none')
    await expect(page.getByRole('link', { name: /Открыть оригинальную запись/ })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    )
    await expect(page.locator('.message time').first()).toHaveText('2026-01-01T12:00:00+05:00')
    await expect(page.getByText(/Интонация и дикция не анализировались/)).toBeVisible()
    await page
      .locator('audio')
      .evaluate((el) => el.dispatchEvent(new Event('error', { bubbles: false })))
    await expect(page.getByRole('alert')).toContainText('Не удалось воспроизвести')
    for (const path of [
      '/',
      '/conversations',
      '/checklists/1',
      '/appeals',
      `/appeals/${appealId}`,
      '/ai-jobs',
      '/ai-jobs/1',
      '/ai-batches/1',
      '/datasets',
    ]) {
      await goto(page, path)
      await expect(page.getByLabel('Состояние сервисов').last()).toContainText('AI Worker Offline')
    }
  })
  test('Keyboard: menu, focusable form, modal Escape and focus restore', async ({ page }) => {
    await goto(page, '/conversations')
    await page.getByRole('link', { name: 'Перейти к содержимому' }).focus()
    await page.keyboard.press('Enter')
    await expect(page.locator('main')).toBeFocused()
    await expect(page).toHaveURL(/#\/conversations$/)
    const button = page.getByRole('button', {
      name: 'Оценить SYNTHETIC-UI-001',
      exact: true,
    })
    await button.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Tab')
    expect(
      await page.evaluate(() => document.querySelector('dialog').contains(document.activeElement)),
    ).toBe(true)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(button).toBeFocused()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: 'Открыть меню', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Открыть меню', exact: true })).toBeFocused()
  })
  test('Backend offline, safe errors, empty and loading states', async ({ page }) => {
    await page.route(`${api}/**`, (r) => r.abort())
    await goto(page, '/')
    await expect(page.getByRole('alert')).toContainText('Нет соединения с backend')
    await expect(page.getByLabel('Состояние сервисов').last()).toContainText('Backend Offline')
    await page.unroute(`${api}/**`)
    await page.route(`${api}/conversations?**`, async (r) => {
      await new Promise((resolve) => setTimeout(resolve, 300))
      await r.fulfill({ json: { items: [], total: 0, limit: 100, offset: 0 } })
    })
    await goto(page, '/conversations')
    await expect(page.getByRole('status', { name: 'Загрузка данных' })).toBeVisible()
    await expect(page.getByText('Диалоги пока не импортированы.')).toBeVisible()
  })
  test('All pages responsive 1440/1280/768/390, no page errors, synthetic screenshots', async ({
    page,
  }, info) => {
    test.setTimeout(120000)
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    for (const width of [1440, 1280, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      for (const path of [
        '/',
        '/conversations',
        '/evaluations/1',
        '/checklists/1',
        '/appeals',
        `/appeals/${appealId}`,
        '/ai-jobs',
        '/ai-jobs/1',
        '/ai-batches/1',
        '/datasets',
      ]) {
        await goto(page, path)
        await expect(page.getByLabel('Состояние сервисов').last()).toContainText('Backend Online')
        await noOverflow(page)
      }
      await goto(page, '/checklists/1')
      await page.getByRole('button', { name: 'Создать новую версию' }).click()
      await expect(page.locator('.editor-criterion')).toHaveCount(8)
      await noOverflow(page)
      await page.screenshot({
        path: info.outputPath(`checklist-${width}.png`),
        fullPage: false,
      })
      await goto(page, '/evaluations/1')
      await expect(page.locator('.criterion-result')).toHaveCount(8)
      await page
        .getByRole('button', { name: /Цитата/ })
        .first()
        .click()
      await expect(page.locator('#message-4')).toBeInViewport()
      await noOverflow(page)
      await page.screenshot({
        path: info.outputPath(`evaluation-${width}.png`),
        fullPage: false,
      })
      await goto(page, '/')
      await page.screenshot({
        path: info.outputPath(`dashboard-${width}.png`),
        fullPage: false,
      })
    }
    expect(errors).toEqual([])
  })
  test('New checklist with custom scale and N/A, add/remove criteria, immutable save', async ({
    page,
    request,
  }) => {
    await goto(page, '/checklists')
    await page.getByRole('button', { name: 'Создать чек-лист', exact: true }).click()
    await page.getByLabel('Название чек-листа', { exact: true }).fill('UI custom checklist')
    await page
      .getByLabel('Описание чек-листа', { exact: true })
      .fill('Synthetic configuration test')
    await page.getByLabel('Код', { exact: true }).fill('CUSTOM')
    await page.getByLabel('Название', { exact: true }).fill('Custom support')
    await page.getByLabel('Тип', { exact: true }).selectOption('scale')
    await page.getByLabel('Вес', { exact: true }).fill('100')
    await page
      .getByLabel('Описание критерия', { exact: true })
      .fill('Evaluate the configured scale.')
    await page.getByLabel('Допустимые ступени', { exact: true }).fill('0,3,9')
    await page.getByLabel('Максимум шкалы', { exact: true }).fill('9')
    await page.getByLabel('Описание ступени 3', { exact: true }).fill('Partial response')
    await page.getByLabel('Разрешить N/A').check()
    await page.getByLabel('Условие N/A', { exact: true }).fill('Request not formulated')
    await page.getByRole('button', { name: 'Добавить критерий', exact: true }).click()
    await expect(page.locator('.editor-criterion')).toHaveCount(2)
    await expect(
      page.getByRole('button', { name: 'Сохранить чек-лист', exact: true }),
    ).toBeDisabled()
    await page.getByRole('button', { name: 'Удалить критерий', exact: true }).last().click()
    await page.getByRole('button', { name: 'Сохранить чек-лист', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'UI custom checklist', exact: true }),
    ).toBeVisible()
    const id = page.url().split('/').at(-1)
    const version = (await (await request.get(`${api}/checklists/${id}/versions`)).json())[0]
    expect(version.criteria[0]).toMatchObject({
      code: 'CUSTOM',
      weight: '100',
      allowed_values: ['0', '3', '9'],
      max_score: '9',
      allow_na: true,
      scale_labels: { 3: 'Partial response' },
    })
  })
  test('Batch retry only failed preserves cancelled jobs', async ({ page, request }) => {
    await goto(page, '/ai-batches/2')
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
    await expect(page.getByText(/Успешных оценок: 0 из 2/)).toBeVisible()
    await page.getByRole('button', { name: 'Повторить только failed (1)' }).click()
    await expect(page.getByRole('status')).toContainText('Возвращено в очередь: 1')
    const batch = await (await request.get(`${api}/ai/batches/2`)).json()
    expect(batch.queued).toBe(1)
    expect(batch.cancelled).toBe(1)
    expect(batch.completed).toBe(0)
  })
  test('Invalid IDs and missing records show safe errors, not endless loading', async ({
    page,
  }) => {
    await goto(page, '/conversations/abc')
    await expect(page.getByRole('alert')).toContainText('положительный целочисленный ID')
    for (const path of [
      '/conversations/99999',
      '/evaluations/99999',
      '/checklists/99999',
      '/appeals/99999',
      '/ai-jobs/99999',
      '/ai-batches/99999',
    ]) {
      await page.goto(`/#${path}`)
      await expect(page.getByRole('alert').first()).toBeVisible()
    }
  })
  test('Accessibility WCAG A/AA scan: pages, editor and dialog', async ({ page }) => {
    test.setTimeout(120000)
    async function scan() {
      const result = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze()
      expect(
        result.violations.map((v) => ({
          id: v.id,
          count: v.nodes.length,
          nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target, summary: n.failureSummary })),
        })),
      ).toEqual([])
    }
    for (const path of [
      '/',
      '/conversations',
      '/evaluations/1',
      '/checklists/1',
      '/appeals',
      `/appeals/${appealId}`,
      '/ai-jobs',
      '/ai-batches/1',
      '/datasets',
    ]) {
      await goto(page, path)
      await expect(page.getByLabel('Состояние сервисов').last()).toContainText('Backend Online')
      await scan()
    }
    await goto(page, '/checklists/1')
    await page.getByRole('button', { name: 'Создать новую версию' }).click()
    await scan()
    await goto(page, '/conversations')
    await page.getByRole('button', { name: 'Оценить SYNTHETIC-UI-001', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await scan()
  })
})
