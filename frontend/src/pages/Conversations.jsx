import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowUpRight, Search, Sparkles } from 'lucide-react'
import { useWorkspace } from '../hooks/data'
import { latestByConversation, paginate, channelLabel } from '../utils/domain'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Pagination,
  QueryState,
  Score,
  Select,
  StatusBadge,
  Table,
  Tooltip,
} from '../components/ui'
import AIStartDialog from '../components/ai/AIStartDialog'
export function ConversationTable({
  rows,
  selected,
  onSelect,
  datasets,
  evaluations,
  jobs,
  onEvaluate,
}) {
  return (
    <Table
      caption="Диалоги"
      headers={[
        'Выбор',
        'Диалог / набор',
        'Язык',
        'Канал',
        'Реплики',
        'Оценка',
        'AI статус',
        'Действия',
      ]}
    >
      {rows.map((c) => {
        const evaluation = evaluations.get(c.id),
          job = jobs.get(c.id)
        return (
          <tr key={c.id}>
            <td>
              <input
                type="checkbox"
                aria-label={`Выбрать ${c.conversation_id}`}
                checked={selected.has(c.id)}
                onChange={() => onSelect(c.id)}
              />
            </td>
            <td>
              <Link className="strong-link" to={`/conversations/${c.id}`}>
                {c.conversation_id}
              </Link>
              <small>
                {datasets.find((d) => d.id === c.dataset_id)?.group_id || `#${c.dataset_id}`}
              </small>
            </td>
            <td>
              <Badge>{c.language}</Badge>
            </td>
            <td>{channelLabel(c.channel)}</td>
            <td>
              <Tooltip text="API списка не возвращает количество реплик. Точное число есть в карточке.">
                —
              </Tooltip>
            </td>
            <td>
              {evaluation ? (
                <Link to={`/evaluations/${evaluation.id}`}>
                  <Score value={evaluation.final_score} />
                  {evaluation.critical_violation && <Badge tone="failed">Грубое нарушение</Badge>}
                </Link>
              ) : (
                <span className="muted">Не оценён</span>
              )}
            </td>
            <td>
              {job ? (
                <Link to={`/ai-jobs/${job.id}`}>
                  <StatusBadge status={job.status} />
                </Link>
              ) : (
                '—'
              )}
            </td>
            <td>
              <div className="actions">
                <Link
                  className="icon-link"
                  to={`/conversations/${c.id}`}
                  aria-label={`Открыть ${c.conversation_id}`}
                >
                  <ArrowUpRight size={18} />
                </Link>
                <Button
                  variant="ghost"
                  aria-label={`Оценить ${c.conversation_id}`}
                  onClick={() => onEvaluate([c.id])}
                >
                  <Sparkles size={17} />
                </Button>
              </div>
            </td>
          </tr>
        )
      })}
    </Table>
  )
}
export default function Conversations() {
  const query = useWorkspace(),
    data = query.data
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState(new Set())
  const [target, setTarget] = useState(null)
  const latest = latestByConversation(data?.evaluations || [], true),
    jobs = latestByConversation(data?.jobs || [])
  function filter(key, value) {
    // HashRouter updates browser history before concurrent React rendering finishes.
    // Read the current URL so rapid edits cannot restore a previously cleared filter.
    const next = new URLSearchParams(window.location.hash.split('?')[1] || '')
    value ? next.set(key, value) : next.delete(key)
    next.delete('page')
    setParams(next, { replace: true })
    setSelected(new Set())
  }
  const rows = (data?.conversations || []).filter((c) => {
    const e = latest.get(c.id),
      j = jobs.get(c.id)
    return (
      (!params.get('search') ||
        c.conversation_id.toLowerCase().includes(params.get('search').toLowerCase())) &&
      (!params.get('dataset') || c.dataset_id === Number(params.get('dataset'))) &&
      (!params.get('language') || c.language === params.get('language')) &&
      (!params.get('channel') || c.channel === params.get('channel')) &&
      (!params.get('evaluated') || !!e === (params.get('evaluated') === 'yes')) &&
      (!params.get('job') || j?.status === params.get('job')) &&
      (!params.get('critical') || !!e?.critical_violation === (params.get('critical') === 'yes'))
    )
  })
  const page = paginate(rows, params.get('page'))
  const toggle = (id) =>
    setSelected((old) => {
      const next = new Set(old)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  return (
    <>
      <PageHeader
        title="Диалоги"
        description="Все обращения, оценки и доказательства в одном рабочем пространстве."
      >
        <Link className="button secondary" to="/datasets">
          Импорт данных
        </Link>
        <Button disabled={!selected.size} onClick={() => setTarget([...selected])}>
          <Sparkles size={17} />
          Оценить выбранные ({selected.size})
        </Button>
      </PageHeader>
      <QueryState query={query}>
        {data && (
          <Card className="table-card">
            <div className="filters">
              <Field label="Поиск ID">
                <div className="search-field">
                  <Search size={17} />
                  <Input
                    placeholder="Найти диалог…"
                    value={params.get('search') || ''}
                    onChange={(e) => filter('search', e.target.value)}
                  />
                </div>
              </Field>
              <Field label="Набор">
                <Select
                  value={params.get('dataset') || ''}
                  onChange={(e) => filter('dataset', e.target.value)}
                >
                  <option value="">Все наборы</option>
                  {data.datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.group_id}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Язык">
                <Select
                  value={params.get('language') || ''}
                  onChange={(e) => filter('language', e.target.value)}
                >
                  <option value="">Все языки</option>
                  {['RU', 'KZ', 'EN'].map((l) => (
                    <option key={l}>{l}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Канал">
                <Select
                  value={params.get('channel') || ''}
                  onChange={(e) => filter('channel', e.target.value)}
                >
                  <option value="">Все каналы</option>
                  <option value="agent chat">Чат</option>
                  <option value="voice call">Звонок</option>
                </Select>
              </Field>
              <Field label="Наличие оценки">
                <Select
                  value={params.get('evaluated') || ''}
                  onChange={(e) => filter('evaluated', e.target.value)}
                >
                  <option value="">Все</option>
                  <option value="yes">Оценён</option>
                  <option value="no">Не оценён</option>
                </Select>
              </Field>
              <Field label="AI статус">
                <Select
                  value={params.get('job') || ''}
                  onChange={(e) => filter('job', e.target.value)}
                >
                  <option value="">Любой</option>
                  {['queued', 'running', 'completed', 'failed', 'cancelled'].map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Грубое нарушение">
                <Select
                  value={params.get('critical') || ''}
                  onChange={(e) => filter('critical', e.target.value)}
                >
                  <option value="">Все</option>
                  <option value="yes">Есть нарушение</option>
                  <option value="no">Нет флага нарушения</option>
                </Select>
              </Field>
            </div>
            <div className="table-toolbar">
              <span>{rows.length} диалогов · фильтры по всему набору</span>
              <div className="actions">
                <Button
                  variant="ghost"
                  disabled={!rows.length}
                  onClick={() => setSelected(new Set(rows.map((c) => c.id)))}
                >
                  Выбрать все найденные ({rows.length})
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSelected(new Set())
                    setParams({})
                  }}
                >
                  Сбросить
                </Button>
              </div>
            </div>
            {rows.length ? (
              <ConversationTable
                rows={page.items}
                selected={selected}
                onSelect={toggle}
                datasets={data.datasets}
                evaluations={latest}
                jobs={jobs}
                onEvaluate={setTarget}
              />
            ) : (
              <EmptyState
                title={
                  data.conversations.length ? 'Ничего не найдено' : 'Диалоги пока не импортированы.'
                }
              >
                Измените фильтры или импортируйте набор.
              </EmptyState>
            )}
            <Pagination
              {...page}
              onChange={(p) => {
                const n = new URLSearchParams(window.location.hash.split('?')[1] || '')
                n.set('page', p)
                setParams(n)
              }}
            />
          </Card>
        )}
      </QueryState>
      {target && (
        <AIStartDialog
          ids={target}
          checklistId={params.get('checklist_id')}
          onClose={() => setTarget(null)}
        />
      )}
    </>
  )
}
