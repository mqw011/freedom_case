import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { getConversation } from '../api/conversations'
import { getEvaluation } from '../api/evaluations'
import { useVersionCatalog, useWorkspace } from '../hooks/data'
import { channelLabel, evidenceSelection } from '../utils/domain'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  QueryState,
  Select,
  StatusBadge,
} from '../components/ui'
import TranscriptViewer from '../components/conversations/TranscriptViewer'
import AudioPlayer from '../components/conversations/AudioPlayer'
import EvaluationPanel from '../components/evaluations/EvaluationPanel'
import AIStartDialog from '../components/ai/AIStartDialog'
export default function ConversationDetail({ evaluationRoute = false }) {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const workspace = useWorkspace()
  const catalog = useVersionCatalog()
  const direct = useQuery({
    queryKey: ['evaluation', Number(id)],
    queryFn: ({ signal }) => getEvaluation(id, signal),
    enabled: evaluationRoute,
  })
  const cid = evaluationRoute ? direct.data?.conversation_id : Number(id)
  const conversation = useQuery({
    queryKey: ['conversation', cid],
    queryFn: ({ signal }) => getConversation(cid, signal),
    enabled: Number.isSafeInteger(cid) && cid > 0,
  })
  const evaluations = (workspace.data?.evaluations || [])
    .filter((e) => e.conversation_id === cid)
    .sort((a, b) => b.id - a.id)
  const eid = evaluationRoute
    ? Number(id)
    : Number(params.get('evaluation') || evaluations[0]?.id || 0)
  const evaluation = useQuery({
    queryKey: ['evaluation', eid],
    queryFn: ({ signal }) => getEvaluation(eid, signal),
    enabled: Number.isSafeInteger(eid) && eid > 0,
  })
  const [selection, setSelection] = useState(null),
    [error, setError] = useState(null),
    [start, setStart] = useState(false)
  function selectEvidence(e) {
    try {
      const selected = evidenceSelection(conversation.data.messages, e)
      setSelection(selected)
      setError(null)
      requestAnimationFrame(() => {
        const el = document.getElementById(`message-${selected.first}`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el?.focus({ preventScroll: true })
      })
    } catch (err) {
      setError(err)
    }
  }
  const version = catalog.data?.find((v) => v.id === evaluation.data?.checklist_version_id),
    job = workspace.data?.jobs.find((j) => j.evaluation_id === eid)
  const latestJob = [...(workspace.data?.jobs || [])]
    .reverse()
    .find((j) => j.conversation_id === cid)
  if (!Number.isSafeInteger(Number(id)) || Number(id) <= 0)
    return (
      <>
        <PageHeader title="Некорректный идентификатор" />
        <ErrorState error={new Error('Укажите положительный целочисленный ID.')} />
      </>
    )
  return (
    <>
      {evaluationRoute && direct.isError ? (
        <ErrorState error={direct.error} />
      ) : (
        <QueryState query={conversation}>
          {conversation.data && (
            <>
              <PageHeader
                eyebrow={`${conversation.data.language} / ${channelLabel(conversation.data.channel)}`}
                title={conversation.data.conversation_id}
                description={`${conversation.data.messages.length} реплик · исходные timestamps · dataset #${conversation.data.dataset_id}`}
              >
                <Link className="button secondary" to="/conversations">
                  Все диалоги
                </Link>
                <Button onClick={() => setStart(true)}>
                  <Sparkles size={17} />
                  Новая AI-оценка
                </Button>
              </PageHeader>
              {latestJob && latestJob.status !== 'completed' && (
                <div className="notice">
                  <Link to={`/ai-jobs/${latestJob.id}`}>Последнее AI задание #{latestJob.id}</Link>{' '}
                  <StatusBadge status={latestJob.status} />{' '}
                  {latestJob.status === 'failed'
                    ? 'Оценка не завершилась. Причина доступна в AI заданиях.'
                    : latestJob.status === 'queued'
                      ? 'Ожидает обработки worker.'
                      : ''}
                </div>
              )}
              {error && <ErrorState error={error} />}
              <div className="conversation-grid">
                <Card className="transcript-card">
                  <div className="section-heading">
                    <h2>Транскрипт</h2>
                    <Badge>{conversation.data.messages.length} реплик</Badge>
                  </div>
                  {conversation.data.channel === 'voice call' && (
                    <AudioPlayer url={conversation.data.audio_url} />
                  )}
                  <TranscriptViewer
                    key={cid}
                    messages={conversation.data.messages}
                    selection={selection}
                  />
                </Card>
                <Card className="evaluation-card">
                  <div className="section-heading">
                    <h2>Оценка качества</h2>
                  </div>
                  <QueryState query={workspace}>
                    <Field label="История оценок">
                      <Select
                        value={eid || ''}
                        onChange={(e) => {
                          setSelection(null)
                          if (evaluationRoute)
                            window.location.hash = `/evaluations/${e.target.value}`
                          else setParams({ evaluation: e.target.value })
                        }}
                      >
                        <option value="" disabled>
                          Выберите оценку
                        </option>
                        {evaluations.map((e) => (
                          <option value={e.id} key={e.id}>
                            #{e.id} · {e.source} · версия ID {e.checklist_version_id}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </QueryState>
                  {eid ? (
                    <QueryState query={evaluation}>
                      {evaluation.data &&
                        (evaluation.data.conversation_id !== cid ? (
                          <ErrorState
                            error={new Error('Эта оценка относится к другому диалогу.')}
                          />
                        ) : (
                          <>
                            <QueryState query={catalog}>
                              {version && (
                                <Link
                                  className="text-link"
                                  to={`/checklists/${version.checklist_id}?version=${version.id}`}
                                >
                                  Открыть версию чек-листа →
                                </Link>
                              )}
                            </QueryState>
                            <EvaluationPanel
                              key={eid}
                              evaluation={evaluation.data}
                              version={version}
                              job={job}
                              appeals={workspace.data?.appeals.filter(
                                (a) => a.evaluation_id === eid,
                              )}
                              onEvidence={selectEvidence}
                            />
                          </>
                        ))}
                    </QueryState>
                  ) : (
                    <EmptyState title="Оценок пока нет">
                      Запустите AI-оценку. При выключенном worker задание останется в очереди.
                    </EmptyState>
                  )}
                </Card>
              </div>
              {start && <AIStartDialog ids={[cid]} onClose={() => setStart(false)} />}
            </>
          )}
        </QueryState>
      )}
    </>
  )
}
