import Decimal from 'decimal.js'
export const statusLabels = {
  queued: 'В очереди',
  running: 'Выполняется',
  completed: 'Завершено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
  pending: 'Ожидает решения',
  upheld: 'Подтверждено',
  revised: 'Пересмотрено',
}
export const statusLabel = (value) => statusLabels[value] || value || 'Нет данных'
export const answerLabel = (value) =>
  ({ yes: 'Да', no: 'Нет', na: 'N/A' })[value] ?? formatDecimal(value)
export function formatDecimal(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '—'
  try {
    return new Decimal(value).toFixed(digits).replace(/\.00$/, '').replace('.', ',')
  } catch {
    return '—'
  }
}
export const dateLabel = (value) =>
  value
    ? new Intl.DateTimeFormat('ru', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date(value))
    : '—'
export const channelLabel = (value) => (value === 'voice call' ? 'Звонок' : 'Чат')
export function latestByConversation(rows, completedOnly = false) {
  const map = new Map()
  for (const row of rows) {
    if (completedOnly && row.status !== 'completed') continue
    const old = map.get(row.conversation_id)
    const time = new Date((completedOnly && row.completed_at) || row.created_at).getTime()
    const oldTime = old && new Date((completedOnly && old.completed_at) || old.created_at).getTime()
    if (!old || time > oldTime || (time === oldTime && row.id > old.id))
      map.set(row.conversation_id, row)
  }
  return map
}
export function aggregate(data) {
  const latest = [...latestByConversation(data.evaluations, true).values()]
  const scored = latest.filter((e) => e.final_score !== null)
  const average = scored.length
    ? scored
        .reduce((sum, e) => sum.plus(e.final_score), new Decimal(0))
        .div(scored.length)
        .toFixed(2)
    : null
  return {
    latest,
    average,
    excluded: latest.length - scored.length,
    critical: latest.filter((e) => e.critical_violation).length,
    languages: ['RU', 'KZ', 'EN'].map((label) => ({
      label,
      count: data.conversations.filter((c) => c.language === label).length,
    })),
    distribution: [
      { label: '0–49', min: 0, max: 50 },
      { label: '50–74', min: 50, max: 75 },
      { label: '75–89', min: 75, max: 90 },
      { label: '90–100', min: 90, max: 101 },
    ].map((b) => ({
      ...b,
      count: scored.filter(
        (e) => new Decimal(e.final_score).gte(b.min) && new Decimal(e.final_score).lt(b.max),
      ).length,
    })),
  }
}
export function paginate(items, page, size = 15) {
  const pages = Math.max(1, Math.ceil(items.length / size))
  const current = Math.min(pages, Math.max(1, Math.floor(Number(page)) || 1))
  return {
    items: items.slice((current - 1) * size, current * size),
    page: current,
    pages,
    total: items.length,
  }
}
export function evidenceSelection(messages, evidence) {
  if (!evidence.message_id && evidence.evidence_type === 'absence')
    return {
      ids: messages.map((m) => m.id),
      first: messages[0]?.id,
      excerpt: null,
    }
  const start = messages.findIndex((m) => m.id === evidence.message_id)
  const end = evidence.end_message_id
    ? messages.findIndex((m) => m.id === evidence.end_message_id)
    : start
  if (
    start < 0 ||
    end < start ||
    (evidence.excerpt && !messages[start].text.includes(evidence.excerpt))
  )
    throw new Error('Доказательство недоступно: ссылка или цитата не соответствует сообщениям.')
  return {
    ids: messages.slice(start, end + 1).map((m) => m.id),
    first: messages[start].id,
    excerpt: evidence.excerpt,
  }
}
export const readConfig = (c) =>
  Object.fromEntries(
    [
      'code',
      'title',
      'description',
      'section',
      'criterion_type',
      'weight',
      'allowed_values',
      'max_score',
      'allow_na',
      'na_condition',
      'scale_labels',
      'display_order',
    ].map((key) => [key, c[key]]),
  )
export function newCriterion(order = 0) {
  return {
    code: '',
    title: '',
    description: '',
    section: 'Новая секция',
    criterion_type: 'binary',
    weight: '10',
    allowed_values: ['0', '1'],
    max_score: '1',
    allow_na: false,
    na_condition: null,
    scale_labels: {},
    display_order: order,
  }
}
export function weightTotal(criteria) {
  try {
    return criteria
      .filter((c) => c.criterion_type !== 'flag')
      .reduce((s, c) => s.plus(c.weight || 0), new Decimal(0))
      .toString()
  } catch {
    return null
  }
}
export function validateChecklist(criteria) {
  const errors = []
  const codes = new Set()
  const orders = new Set()
  if (!criteria.length || criteria.length > 100) errors.push('Нужно от 1 до 100 критериев.')
  criteria.forEach((c, i) => {
    const prefix = `Критерий ${i + 1}: `
    const add = (m) => errors.push(prefix + m)
    for (const [key, max] of [
      ['code', 40],
      ['title', 300],
      ['description', 10000],
      ['section', 300],
    ])
      if (!String(c[key]).trim() || c[key].trim().length > max)
        add(`${key}: обязательное поле, максимум ${max} символов.`)
    if (codes.has(c.code.trim())) add('повторяющийся код.')
    codes.add(c.code.trim())
    if (!Number.isInteger(c.display_order) || c.display_order < 0 || orders.has(c.display_order))
      add('display_order должен быть уникальным целым числом ≥ 0.')
    orders.add(c.display_order)
    try {
      const validNumber = (v) =>
        /^\d+(\.\d{1,6})?$/.test(String(v)) &&
        String(v).replace('.', '').replace(/^0+/, '').length <= 16
      if (![c.weight, c.max_score, ...c.allowed_values].every(validNumber)) throw Error()
      const weight = new Decimal(c.weight),
        max = new Decimal(c.max_score),
        values = c.allowed_values.map((v) => new Decimal(v))
      if (weight.gt(100) || max.lte(0)) add('вес ≤ 100, максимум шкалы > 0.')
      if (
        values.length < 2 ||
        values.length > 100 ||
        new Set(values.map((v) => v.toString())).size !== values.length ||
        !Decimal.min(...values).eq(0) ||
        !Decimal.max(...values).eq(max)
      )
        add('шкала: уникальные значения от 0 до max_score.')
      if (
        c.criterion_type !== 'scale' &&
        (values.length !== 2 || !values.some((v) => v.eq(1)) || !max.eq(1))
      )
        add('binary/flag требует шкалу 0, 1 и максимум 1.')
      if (c.criterion_type === 'flag' ? !weight.eq(0) || c.allow_na : weight.lte(0))
        add('flag: вес 0 и без N/A; остальные: положительный вес.')
      for (const [key, label] of Object.entries(c.scale_labels))
        if (!values.some((v) => v.eq(key)) || !label.trim() || label.trim().length > 10000)
          add('описания ступеней должны соответствовать шкале и быть непустыми.')
    } catch {
      add('некорректное число: максимум 6 знаков после точки, без отрицательных значений.')
    }
    if (c.allow_na !== !!c.na_condition?.trim() || (c.na_condition?.length || 0) > 10000)
      add('N/A требует непустого условия; иначе условие должно отсутствовать.')
  })
  return errors
}
