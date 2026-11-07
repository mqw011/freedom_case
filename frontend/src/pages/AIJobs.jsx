import { useSearchParams, Link } from 'react-router-dom'
import { useWorkspace } from '../hooks/data'
import { dateLabel, paginate, statusLabel } from '../utils/domain'
import {
  Card,
  EmptyState,
  Field,
  PageHeader,
  Pagination,
  QueryState,
  Select,
  StatusBadge,
  Table,
  Tabs,
} from '../components/ui'
import BackendStatus from '../components/BackendStatus'
import BatchCard from '../components/ai/BatchCard'
export function JobsTable({ jobs, conversations = [] }) {
  return (
    <Table
      caption="AI задания"
      headers={[
        'Задание / диалог',
        'Версия',
        'Модель / provider',
        'Статус',
        'Попытки',
        'Даты',
        'Ошибка / оценка',
        '',
      ]}
    >
      {jobs.map((j) => (
        <tr key={j.id}>
          <td>
            <strong>#{j.id}</strong>
            <small>
              <Link to={`/conversations/${j.conversation_id}`}>
                {conversations.find((c) => c.id === j.conversation_id)?.conversation_id ||
                  `Диалог #${j.conversation_id}`}
              </Link>
            </small>
          </td>
          <td>#{j.checklist_version_id}</td>
          <td>
            {j.model}
            <small>{j.provider}</small>
          </td>
          <td>
            <StatusBadge status={j.status} />
            {j.cancel_requested && <small>Отмена запрошена</small>}
          </td>
          <td>
            {j.attempts} / {j.max_attempts}
          </td>
          <td>
            <small>Создано: {dateLabel(j.created_at)}</small>
            <small>Начато: {dateLabel(j.started_at)}</small>
            <small>Завершено: {dateLabel(j.completed_at)}</small>
          </td>
          <td>
            {j.error_code && <code>{j.error_code}</code>}
            {j.evaluation_id ? (
              <Link to={`/evaluations/${j.evaluation_id}`}>Оценка #{j.evaluation_id}</Link>
            ) : (
              !j.error_code && '—'
            )}
          </td>
          <td>
            <Link to={`/ai-jobs/${j.id}`}>Открыть →</Link>
          </td>
        </tr>
      ))}
    </Table>
  )
}
export default function AIJobs() {
  const query = useWorkspace(),
    [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'jobs',
    status = params.get('status') || ''
  const rows = [
      ...(tab === 'jobs'
        ? (query.data?.jobs || []).filter((j) => !status || j.status === status)
        : query.data?.batches || []),
    ].reverse(),
    page = paginate(rows, params.get('page'))
  return (
    <>
      <PageHeader
        title="AI задания"
        description="Настоящее состояние очереди, без ожидания inference на странице."
      >
        <Link className="button primary" to="/conversations">
          Выбрать диалоги
        </Link>
      </PageHeader>
      <Card>
        <BackendStatus />
        <p className="muted">
          Если worker offline, задания остаются в очереди. Исторические результаты, чек-листы и
          апелляции доступны.
        </p>
      </Card>
      <Tabs
        value={tab}
        options={['jobs', 'batches'].map((v) => [v, v === 'jobs' ? 'Задания' : 'Пакеты'])}
        onChange={(v) => setParams({ tab: v })}
      />
      <Card>
        {tab === 'jobs' && (
          <Field label="Статус задания">
            <Select value={status} onChange={(e) => setParams({ tab, status: e.target.value })}>
              <option value="">Все статусы</option>
              {['queued', 'running', 'completed', 'failed', 'cancelled'].map((s) => (
                <option value={s} key={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <QueryState query={query}>
          {rows.length ? (
            tab === 'jobs' ? (
              <JobsTable jobs={page.items} conversations={query.data.conversations} />
            ) : (
              page.items.map((b) => <BatchCard key={b.id} batch={b} />)
            )
          ) : (
            <EmptyState title="Заданий пока нет">
              Выберите диалоги и поставьте их в очередь.
            </EmptyState>
          )}
        </QueryState>
        <Pagination {...page} onChange={(p) => setParams({ tab, status, page: p })} />
      </Card>
    </>
  )
}
