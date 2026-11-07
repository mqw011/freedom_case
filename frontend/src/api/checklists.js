import { apiRequest, getAll, post } from './client'
export const getChecklists = (signal) => getAll('/checklists', signal)
export const getVersions = (id, signal) => apiRequest(`/checklists/${id}/versions`, { signal })
export const createChecklist = (data) => post('/checklists', data)
export const createVersion = (id, criteria) => post(`/checklists/${id}/versions`, { criteria })
export const activateVersion = (id, version_id) =>
  post(`/checklists/${id}/activate`, { version_id })
