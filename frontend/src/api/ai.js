import { apiRequest, queryString as query, post, getAll } from './client'

// Decimal scores and percentages are JSON strings; job IDs are numeric.
export const getAIHealth = (signal) => apiRequest('/ai/health', { signal })
export const createAIJob = (data, signal) => post('/ai/evaluations', data, signal)
export const createAIBatch = (data, signal) => post('/ai/batches', data, signal)
export const getAIJobs = (params, signal) => apiRequest(`/ai/jobs?${query(params)}`, { signal })
export const getAIJob = (id, signal) => apiRequest(`/ai/jobs/${id}`, { signal })
export const getAIJobAttempts = (id, params, signal) =>
  apiRequest(`/ai/jobs/${id}/attempts?${query(params)}`, { signal })
export const retryAIJob = (id, signal) => post(`/ai/jobs/${id}/retry`, undefined, signal)
export const cancelAIJob = (id, signal) => post(`/ai/jobs/${id}/cancel`, undefined, signal)
export const getAIBatches = (params, signal) =>
  apiRequest(`/ai/batches?${query(params)}`, { signal })
export const getAIBatch = (id, signal) => apiRequest(`/ai/batches/${id}`, { signal })
export const getAIBatchJobs = (id, params, signal) =>
  apiRequest(`/ai/batches/${id}/jobs?${query(params)}`, { signal })
export const retryFailedAIJobs = (id, signal) =>
  post(`/ai/batches/${id}/retry-failed`, undefined, signal)

export const getAllJobs = (signal) => getAll('/ai/jobs', signal)
export const getAllBatches = (signal) => getAll('/ai/batches', signal)
