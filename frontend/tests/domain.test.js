import { describe, expect, it } from 'vitest'
import {
  aggregate,
  answerLabel,
  evidenceSelection,
  formatDecimal,
  latestByConversation,
  newCriterion,
  paginate,
  readConfig,
  statusLabel,
  validateChecklist,
  weightTotal,
} from '../src/utils/domain'
const criterion = (overrides = {}) => ({
  ...newCriterion(),
  code: 'custom',
  title: 'Test',
  description: 'Synthetic',
  section: 'Test',
  ...overrides,
})
describe('Display and aggregation without alternate scoring', () => {
  it.each([
    [null, '—'],
    [undefined, '—'],
    ['', '—'],
    ['81.88', '81,88'],
    ['0', '0'],
    ['100', '100'],
    ['bad', '—'],
  ])('formats %s as %s', (v, expected) => expect(formatDecimal(v)).toBe(expected))
  it('distinguishes N/A, negative answer and score zero', () => {
    expect(answerLabel('na')).toBe('N/A')
    expect(answerLabel('no')).toBe('Нет')
    expect(answerLabel('0')).toBe('0')
  })
  it('never translates failed/cancelled into completed', () => {
    expect(statusLabel('failed')).toBe('Ошибка')
    expect(statusLabel('cancelled')).toBe('Отменено')
    expect(statusLabel('queued')).toBe('В очереди')
  })
  it('selects newest completed evaluation and excludes null without excluding zero', () => {
    const e = (id, c, score, status = 'completed') => ({
      id,
      conversation_id: c,
      final_score: score,
      status,
      created_at: `2026-01-${String(id).padStart(2, '0')}T00:00:00Z`,
    })
    const data = {
      conversations: Array.from({ length: 65 }, (_, i) => ({
        language: i < 35 ? 'RU' : i < 50 ? 'KZ' : 'EN',
      })),
      evaluations: [
        e(1, 1, '20'),
        e(2, 1, '100'),
        e(3, 2, '0'),
        e(4, 3, null),
        e(5, 4, '0', 'failed'),
      ],
    }
    const result = aggregate(data)
    expect(result.average).toBe('50.00')
    expect(result.latest).toHaveLength(3)
    expect(result.excluded).toBe(1)
    expect(result.languages.map((x) => x.count)).toEqual([35, 15, 15])
    expect(result.distribution.map((x) => x.count)).toEqual([1, 0, 0, 1])
  })
  it('uses job creation, not older job completion, for latest job', () =>
    expect(
      latestByConversation([
        {
          id: 1,
          conversation_id: 1,
          created_at: '2026-01-01',
          completed_at: '2026-01-03',
        },
        { id: 2, conversation_id: 1, created_at: '2026-01-02' },
      ]).get(1).id,
    ).toBe(2))
  it('paginates all data and clamps fractional/out of range pages', () => {
    const rows = Array.from({ length: 65 }, (_, i) => i)
    expect(paginate(rows, 5).items).toEqual([60, 61, 62, 63, 64])
    expect(paginate(rows, 100).page).toBe(5)
    expect(paginate(rows, 2.5).page).toBe(2)
    expect(paginate([], 0).pages).toBe(1)
  })
})
describe('Checklist configuration matches backend, weights use Decimal', () => {
  it('sums decimal weights exactly and ignores flag', () =>
    expect(
      weightTotal([
        criterion({ weight: '0.1' }),
        criterion({ weight: '0.2' }),
        criterion({ criterion_type: 'flag', weight: '0' }),
      ]),
    ).toBe('0.3'))
  it('accepts binary and custom scale', () => {
    expect(validateChecklist([criterion()])).toEqual([])
    expect(
      validateChecklist([
        criterion({
          criterion_type: 'scale',
          allowed_values: ['0', '3', '9'],
          max_score: '9',
          scale_labels: { 3: 'Partial' },
        }),
      ]),
    ).toEqual([])
  })
  it('allows unordered steps because backend does', () =>
    expect(
      validateChecklist([
        criterion({
          criterion_type: 'scale',
          allowed_values: ['9', '0', '3'],
          max_score: '9',
        }),
      ]),
    ).toEqual([]))
  it.each([
    { weight: '-1' },
    { weight: '0' },
    { weight: '101' },
    { allowed_values: ['0', '0', '1'] },
    { max_score: '2' },
    { allow_na: true },
    { na_condition: 'unused' },
    { criterion_type: 'flag', weight: '1' },
    { criterion_type: 'flag', weight: '0', allow_na: true, na_condition: 'x' },
    { scale_labels: { 2: 'Unknown' } },
    { title: '' },
    { weight: '0.1234567' },
  ])('rejects inconsistent criterion %j', (change) =>
    expect(validateChecklist([criterion(change)]).length).toBeGreaterThan(0),
  )
  it('accepts N/A only with condition', () =>
    expect(validateChecklist([criterion({ allow_na: true, na_condition: 'No request' })])).toEqual(
      [],
    ))
  it('rejects duplicate codes and order', () => {
    expect(validateChecklist([criterion(), criterion()]).join()).toMatch(/код/)
    expect(validateChecklist([criterion(), criterion({ code: 'new' })]).join()).toMatch(
      /display_order/,
    )
  })
  it('does not change originals when cloning a version and drops private editor state', () => {
    const original = criterion({ id: 5, _labelsInvalid: true })
    const copy = readConfig(original)
    copy.weight = '25'
    expect(original.weight).toBe('10')
    expect(copy).not.toHaveProperty('id')
    expect(copy).not.toHaveProperty('_labelsInvalid')
  })
})
describe('Evidence ID mapping', () => {
  const messages = [
    { id: 30, text: 'Сәлеметсіз бе! Hello', message_index: 0 },
    { id: 4, text: 'Second', message_index: 1 },
    { id: 90, text: 'Last', message_index: 2 },
  ]
  it('preserves exact multilingual quote', () =>
    expect(
      evidenceSelection(messages, {
        evidence_type: 'quote',
        message_id: 30,
        excerpt: 'Сәлеметсіз бе!',
      }),
    ).toEqual({ ids: [30], first: 30, excerpt: 'Сәлеметсіз бе!' }))
  it('maps ranges by transcript order, not numeric ID', () =>
    expect(
      evidenceSelection(messages, {
        evidence_type: 'range',
        message_id: 30,
        end_message_id: 4,
      }).ids,
    ).toEqual([30, 4]))
  it('maps bounded absence and whole-dialog absence', () => {
    expect(
      evidenceSelection(messages, {
        evidence_type: 'absence',
        message_id: 4,
        end_message_id: 90,
      }).ids,
    ).toEqual([4, 90])
    expect(evidenceSelection(messages, { evidence_type: 'absence' }).ids).toEqual([30, 4, 90])
  })
  it.each([
    { message_id: 999 },
    { message_id: 30, excerpt: 'fabricated' },
    { message_id: 90, end_message_id: 30 },
  ])('rejects damaged evidence %j', (e) =>
    expect(() => evidenceSelection(messages, e)).toThrow(/недоступно/),
  )
})
