const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export async function apiRequest(path, { signal, ...options } = {}) {
  const timeout = AbortSignal.timeout(10000)
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: { Accept: 'application/json', ...options.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(body?.error?.message || `HTTP ${response.status}`, response.status, body?.error?.code)
  }
  return body
}

export const getHealth = (signal) => apiRequest('/health', { signal })
