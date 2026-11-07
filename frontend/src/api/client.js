const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api').replace(
  /\/$/,
  '',
)
export class ApiError extends Error {
  constructor(message, status = 0, code = 'network_error', details = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}
export function responseError(body, status) {
  return new ApiError(
    body?.error?.message || `Ошибка сервера: HTTP ${status}`,
    status,
    body?.error?.code || 'http_error',
    body?.error?.details,
  )
}
export async function apiRequest(path, { signal, timeoutMs = 15000, ...options } = {}) {
  const timeout = AbortSignal.timeout(timeoutMs)
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { Accept: 'application/json', ...options.headers },
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw responseError(body, response.status)
    if (body === null)
      throw new ApiError('Сервер вернул некорректный ответ', 502, 'invalid_response')
    return body
  } catch (error) {
    if (signal?.aborted) throw error
    if (error instanceof ApiError) throw error
    throw new ApiError(
      timeout.aborted
        ? 'Время ожидания истекло. Проверьте результат перед повтором действия.'
        : 'Нет соединения с backend. Проверьте доступность сервиса.',
      0,
      timeout.aborted ? 'timeout' : 'network_error',
    )
  }
}
export const queryString = (params = {}) =>
  new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
export const post = (path, data, signal, options = {}) =>
  apiRequest(path, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
    ...options,
  })
export async function getAll(path, signal, params = {}) {
  const items = []
  let offset = 0
  while (true) {
    const page = await apiRequest(`${path}?${queryString({ ...params, offset, limit: 100 })}`, {
      signal,
    })
    if (!Array.isArray(page.items) || !Number.isInteger(page.total))
      throw new ApiError('Некорректная страница данных', 502, 'invalid_page')
    items.push(...page.items)
    offset += page.items.length
    if (offset >= page.total) return items
    if (!page.items.length)
      throw new ApiError('Набор данных изменился. Обновите страницу.', 409, 'incomplete_page')
  }
}
export const getHealth = (signal) => apiRequest('/health', { signal })
