import { useQueries } from '@tanstack/react-query'
import { getEvaluation } from '../api/evaluations'
import { useSearchParams, Link } from 'react-router-dom'
import { useWorkspace } from '../hooks/data'
import { answerLabel, dateLabel, paginate } from '../utils/domain'
import {
  Card,
  EmptyState,
  Field,
  ErrorState,
  PageHeader,
  Pagination,
  QueryState,
  Select,
  StatusBadge,
  Table,
} from '../components/ui'
export default function Appeals() {
  const query = useWorkspace()
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || ''
  const details = useQueries({
    queries: [...new Set((query.data?.appeals || []).map((a) => a.evaluation_id))].map((id) => ({
      queryKey: ['evaluation', id],
      queryFn: ({ signal }) => getEvaluation(id, signal),
    })),
  })
  const rows = [...(query.data?.appeals || [])]
      .filter((a) => !status || a.status === status)
      .reverse(),
    page = paginate(rows, params.get('page'))
  return (
    <>
      <PageHeader
        title="Апелляции"
        description="Каждое решение сохраняет исходную оценку и объясняет пересмотр."
      />
      <Card>
        <Field label="Статус апелляции">
          <Select
            value={status}
            onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}
          >
            <option value="">Все статусы</option>
            <option value="pending">Ожидает решения</option>
            <option value="upheld">Подтверждено</option>
            <option value="revised">Пересмотрено</option>
          </Select>
        </Field>
        {details.some((d) => d.isError) && (
          <ErrorState
            error={
              new Error(
                'Не удалось получить часть исходных ответов. Откройте апелляцию или повторите загрузку.',
              )
            }
            retry={() => details.forEach((d) => d.refetch())}
          />
        )}
        <QueryState query={query}>
          {rows.length ? (
            <Table
              caption="Апелляции"
              headers={[
                'Апелляция',
                'Диалог / оценка',
                'Критерий',
                'Статус',
                'Ответ до → после',
                'Создана',
                '',
              ]}
            >
              {page.items.map((a) => {
                const e = query.data.evaluations.find((v) => v.id === a.evaluation_id),
                  c = query.data.conversations.find((v) => v.id === e?.conversation_id),
                  detail = details.find((d) => d.data?.id === a.evaluation_id),
                  result = detail?.data?.results.find((r) => r.id === a.criterion_result_id)
                return (
                  <tr key={a.id}>
                    <td>
                      <strong>#{a.id}</strong>
                    </td>
                    <td>
                      {c?.conversation_id || '—'}
                      <small>Оценка #{a.evaluation_id}</small>
                    </td>
                    <td>
                      {result
                        ? `Критерий ${result.criterion_code}`
                        : details.some((d) => d.isError)
                          ? 'Критерий недоступен'
                          : 'Загрузка критерия…'}
                    </td>
                    <td>
                      <StatusBadge status={a.status} />
                    </td>
                    <td>
                      {a.decision
                        ? `${answerLabel(a.decision.original_answer)} → ${answerLabel(a.decision.revised_answer)}`
                        : result
                          ? answerLabel(result.answer)
                          : '—'}
                    </td>
                    <td>{dateLabel(a.created_at)}</td>
                    <td>
                      <Link to={`/appeals/${a.id}`}>Рассмотреть →</Link>
                    </td>
                  </tr>
                )
              })}
            </Table>
          ) : (
            <EmptyState title="Активных апелляций нет.">
              Апелляцию можно подать из карточки оценки.
            </EmptyState>
          )}
        </QueryState>
        <Pagination
          {...page}
          onChange={(p) => setParams({ ...(status ? { status } : {}), page: p })}
        />
      </Card>
    </>
  )
}
