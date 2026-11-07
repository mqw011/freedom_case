import { apiRequest, getAll, post } from './client'
export const getAppeals = (signal) => getAll('/appeals', signal)
export const getAppeal = (id, signal) => apiRequest(`/appeals/${id}`, { signal })
export const createAppeal = (id, data) => post(`/evaluations/${id}/appeals`, data)
export const decideAppeal = (id, data) => post(`/appeals/${id}/decision`, data)
