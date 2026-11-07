import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getConversations } from '../api/conversations'
import { getDatasets } from '../api/datasets'
import { getEvaluations } from '../api/evaluations'
import { getChecklists, getVersions } from '../api/checklists'
import { getAppeals } from '../api/appeals'
import { getAllJobs, getAllBatches, getAIHealth } from '../api/ai'
import { getHealth } from '../api/client'
export function useWorkspace() {
  return useQuery({
    queryKey: ['workspace'],
    queryFn: async ({ signal }) => {
      const [conversations, datasets, checklists, appeals, jobs, batches] = await Promise.all([
        getConversations(signal),
        getDatasets(signal),
        getChecklists(signal),
        getAppeals(signal),
        getAllJobs(signal),
        getAllBatches(signal),
      ])
      const evaluations = await getEvaluations(signal)
      return {
        conversations,
        datasets,
        evaluations,
        checklists,
        appeals,
        jobs,
        batches,
      }
    },
    refetchInterval: (q) =>
      q.state.data?.jobs.some((j) => ['queued', 'running'].includes(j.status)) ? 5000 : false,
  })
}
export function useHealth() {
  const backend = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 15000,
    retry: false,
  })
  const ai = useQuery({
    queryKey: ['ai-health'],
    queryFn: ({ signal }) => getAIHealth(signal),
    refetchInterval: 15000,
    retry: false,
  })
  return { backend, ai }
}
export function useAction(fn) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      cache.invalidateQueries({
        predicate: (q) => !q.queryKey[0].includes('health'),
      }),
    onError: (error) => {
      if (error.status === 409)
        return cache.invalidateQueries({
          predicate: (q) => !q.queryKey[0].includes('health'),
        })
    },
  })
}
export function useVersionCatalog(enabled = true) {
  const workspace = useWorkspace()
  return useQuery({
    queryKey: [
      'version-catalog',
      workspace.data?.checklists.map((c) => [c.id, c.active_version_id]),
    ],
    enabled: enabled && !!workspace.data,
    queryFn: async ({ signal }) =>
      (await Promise.all(workspace.data.checklists.map((c) => getVersions(c.id, signal)))).flat(),
  })
}
