import { apiRequest } from './client'

const query = (params = {}) => new URLSearchParams(
  Object.entries(params).filter(([, value]) => value !== null && value !== undefined),
).toString()
const post = (path, data, signal) => apiRequest(path, {
  method: 'POST', signal,
  headers: { 'Content-Type': 'application/json' },
  body: data === undefined ? undefined : JSON.stringify(data),
})

// Decimal scores and percentages are JSON strings; job IDs are numeric.
export const getAIHealth = (signal) => apiRequest('/ai/health', { signal })
export const createAIJob = (data, signal) => post('/ai/evaluations', data, signal)
export const createAIBatch = (data, signal) => post('/ai/batches', data, signal)
export const getAIJobs = (params, signal) => apiRequest(`/ai/jobs?${query(params)}`, { signal })
export const getAIJob = (id, signal) => apiRequest(`/ai/jobs/${id}`, { signal })
export const getAIJobAttempts = (id, params, signal) => apiRequest(`/ai/jobs/${id}/attempts?${query(params)}`, { signal })
export const retryAIJob = (id, signal) => post(`/ai/jobs/${id}/retry`, undefined, signal)
export const cancelAIJob = (id, signal) => post(`/ai/jobs/${id}/cancel`, undefined, signal)
export const getAIBatches = (params, signal) => apiRequest(`/ai/batches?${query(params)}`, { signal })
export const getAIBatch = (id, signal) => apiRequest(`/ai/batches/${id}`, { signal })
export const getAIBatchJobs = (id, params, signal) => apiRequest(`/ai/batches/${id}/jobs?${query(params)}`, { signal })
export const retryFailedAIJobs = (id, signal) => post(`/ai/batches/${id}/retry-failed`, undefined, signal)
