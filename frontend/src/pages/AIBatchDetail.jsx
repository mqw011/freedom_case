import { useState } from 'react'
import { paginate } from '../utils/domain'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getAIBatch, retryFailedAIJobs } from '../api/ai'
import { useAction, useWorkspace } from '../hooks/data'
import { Button, Card, ErrorState, PageHeader, Pagination, QueryState } from '../components/ui'
import BatchCard from '../components/ai/BatchCard'
import { JobsTable } from './AIJobs'
export default function AIBatchDetail() {
  const { id } = useParams(),
    workspace = useWorkspace()
  const [current, setCurrent] = useState(1)
  const page = paginate(
    (workspace.data?.jobs || []).filter((j) => j.batch_id === Number(id)),
    current,
  )
  const batch = useQuery({
    queryKey: ['batch', id],
    queryFn: ({ signal }) => getAIBatch(id, signal),
    refetchInterval: (q) => (q.state.data?.queued || q.state.data?.running ? 5000 : false),
  })
  const action = useAction(() => retryFailedAIJobs(id))
  return (
    <>
      <PageHeader
        title={`Пакет #${id}`}
        description="Прогресс рассчитывается по состоянию каждого задания."
      >
        <Link to="/ai-jobs?tab=batches" className="button secondary">
          Все пакеты
        </Link>
      </PageHeader>
      <QueryState query={batch}>
        {batch.data && (
          <Card>
            <BatchCard batch={batch.data} />
            <Button
              disabled={!batch.data.failed || action.isPending}
              onClick={() => action.mutate()}
            >
              Повторить только failed ({batch.data.failed})
            </Button>
            {action.isSuccess && <p role="status">Возвращено в очередь: {action.data.retried}</p>}
            {action.error && <ErrorState error={action.error} />}
          </Card>
        )}
      </QueryState>
      <Card>
        <QueryState query={workspace}>
          {workspace.data && (
            <JobsTable jobs={page.items} conversations={workspace.data.conversations} />
          )}
        </QueryState>
        <Pagination {...page} onChange={setCurrent} />
      </Card>
    </>
  )
}
