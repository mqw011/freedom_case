import { afterEach, expect, it, vi } from 'vitest'
import { apiRequest, getAll, post, responseError } from '../src/api/client'
afterEach(() => vi.unstubAllGlobals())
const response = (body, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
})
it.each([400, 404, 409, 422, 502, 503])('parses safe error HTTP %i', (status) => {
  const e = responseError(
    { error: { code: 'safe_code', message: 'Safe message', details: null } },
    status,
  )
  expect(e.status).toBe(status)
  expect(e.code).toBe('safe_code')
  expect(e.message).toBe('Safe message')
})
it('handles non-JSON failures safely', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(null, false, 503)))
  await expect(apiRequest('/test')).rejects.toMatchObject({
    status: 503,
    code: 'http_error',
  })
})
it('does not reveal network URLs in errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private URL with secret')))
  await expect(apiRequest('/test')).rejects.toMatchObject({
    code: 'network_error',
    message: expect.not.stringContaining('secret'),
  })
})
it('honors cancellation', async () => {
  const controller = new AbortController()
  controller.abort()
  const error = new DOMException('Aborted', 'AbortError')
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(error))
  await expect(apiRequest('/test', { signal: controller.signal })).rejects.toBe(error)
})
it('classifies timeout without dumping provider error', async () => {
  const aborted = new AbortController()
  aborted.abort()
  vi.spyOn(AbortSignal, 'timeout').mockReturnValue(aborted.signal)
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('secret')))
  await expect(apiRequest('/test')).rejects.toMatchObject({ code: 'timeout' })
})
it('fetches all pages beyond the first 100', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(response({ total: 205, items: Array(100).fill(1) }))
    .mockResolvedValueOnce(response({ total: 205, items: Array(100).fill(2) }))
    .mockResolvedValueOnce(response({ total: 205, items: Array(5).fill(3) }))
  vi.stubGlobal('fetch', fetch)
  expect(await getAll('/conversations')).toHaveLength(205)
  expect(fetch.mock.calls[2][0]).toContain('offset=200')
})
it('rejects incomplete pagination instead of displaying false totals', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ total: 10, items: [] })))
  await expect(getAll('/conversations')).rejects.toMatchObject({
    code: 'incomplete_page',
  })
})
it('sends exact decimal strings, not rounded numbers', async () => {
  const fetch = vi.fn().mockResolvedValue(response({ id: 1 }))
  vi.stubGlobal('fetch', fetch)
  await post('/test', { revised_answer: '7.123456' })
  expect(JSON.parse(fetch.mock.calls[0][1].body).revised_answer).toBe('7.123456')
})
