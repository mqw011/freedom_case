import { apiRequest, getAll } from './client'
export const getConversations = (signal) => getAll('/conversations', signal)
export const getConversation = (id, signal) => apiRequest(`/conversations/${id}`, { signal })
