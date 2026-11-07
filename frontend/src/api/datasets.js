import { apiRequest, getAll, post } from './client'
export const getDatasets = (signal) => getAll('/datasets', signal)
export const importGroup = (group_id) =>
  post('/datasets/import', { group_id }, undefined, { timeoutMs: 120000 })
export const importFile = (file) => {
  const body = new FormData()
  body.append('file', file)
  return apiRequest('/datasets/import-json', {
    method: 'POST',
    body,
    timeoutMs: 120000,
  })
}
