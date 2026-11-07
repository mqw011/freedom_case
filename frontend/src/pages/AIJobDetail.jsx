import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getAIJob } from '../api/ai'
import { getAll } from '../api/client'
import { Card, PageHeader, QueryState, StatusBadge, Table, EmptyState } from '../components/ui'
import { dateLabel } from '../utils/domain'
import JobActions from '../components/ai/JobActions'
export default function AIJobDetail() {
  const { id } = useParams()
  const job = useQuery({
    queryKey: ['job', id],
    queryFn: ({ signal }) => getAIJob(id, signal),
    refetchInterval: (q) => (['queued', 'running'].includes(q.state.data?.status) ? 4000 : false),
  })
  const attempts = useQuery({
    queryKey: ['attempts', id, job.data?.status, job.data?.attempts],
    queryFn: ({ signal }) => getAll(`/ai/jobs/${id}/attempts`, signal),
  })
  return (
    <>
      <PageHeader
        title={`AI задание #${id}`}
        description="Закреплённая конфигурация, результат и история выполнения."
      >
        <Link className="button secondary" to="/ai-jobs">
          Все задания
        </Link>
      </PageHeader>
      <QueryState query={job}>
        {job.data && (
          <>
            <Card>
              <div className="section-heading">
                <StatusBadge status={job.data.status} />
                <JobActions job={job.data} />
              </div>
              <dl className="metadata">
                <dt>Диалог</dt>
                <dd>
                  <Link to={`/conversations/${job.data.conversation_id}`}>
                    #{job.data.conversation_id}
                  </Link>
                </dd>
                <dt>Версия чек-листа</dt>
                <dd>#{job.data.checklist_version_id}</dd>
                <dt>Модель / provider</dt>
                <dd>
                  {job.data.model} / {job.data.provider}
                </dd>
                <dt>Попытки</dt>
                <dd>
                  {job.data.attempts} / {job.data.max_attempts}
                </dd>
                <dt>Создано / начато</dt>
                <dd>
                  {dateLabel(job.data.created_at)} / {dateLabel(job.data.started_at)}
                </dd>
                <dt>Завершено</dt>
                <dd>{dateLabel(job.data.completed_at)}</dd>
              </dl>
              {job.data.safe_error_message && (
                <div className="notice danger" role="alert">
                  {job.data.safe_error_message}
                  <small>{job.data.error_code}</small>
                </div>
              )}
              {job.data.status === 'failed' && (
                <p>Оценка не создана. Ошибка задания не означает нулевой балл.</p>
              )}
              {job.data.cancel_requested && job.data.status === 'running' && (
                <p role="status">Ожидается подтверждение отмены от worker.</p>
              )}
              {job.data.diagnostics.needs_human_review && (
                <p className="notice">Результат требует проверки человеком.</p>
              )}
              <dl className="metadata">
                <dt>Длительность, мс</dt>
                <dd>{job.data.diagnostics.latency_ms ?? '—'}</dd>
                <dt>Входные / выходные токены</dt>
                <dd>
                  {job.data.diagnostics.input_tokens ?? '—'} /{' '}
                  {job.data.diagnostics.output_tokens ?? '—'}
                </dd>
                <dt>Фрагменты контекста</dt>
                <dd>{job.data.diagnostics.chunk_count ?? '—'}</dd>
              </dl>
            </Card>
            <Card>
              <h2>История попыток</h2>
              <QueryState query={attempts}>
                {attempts.data?.length ? (
                  <Table
                    caption="Попытки задания"
                    headers={['Попытка', 'Статус', 'Начало', 'Окончание', 'Ошибка']}
                  >
                    {attempts.data.map((a) => (
                      <tr key={a.attempt_number}>
                        <td>{a.attempt_number}</td>
                        <td>{a.status}</td>
                        <td>{dateLabel(a.started_at)}</td>
                        <td>{dateLabel(a.finished_at)}</td>
                        <td>{a.error_code || '—'}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <EmptyState title="Попыток ещё не было" />
                )}
              </QueryState>
            </Card>
          </>
        )}
      </QueryState>
    </>
  )
}
