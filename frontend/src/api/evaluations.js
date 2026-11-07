import { apiRequest, getAll } from './client'
export const getEvaluations = (signal) => getAll('/evaluations', signal)
export const getEvaluation = (id, signal) => apiRequest(`/evaluations/${id}`, { signal })
