import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getAppeal, decideAppeal } from '../api/appeals'
import { getEvaluation } from '../api/evaluations'
import { getConversation } from '../api/conversations'
import { useAction, useVersionCatalog, useWorkspace } from '../hooks/data'
import { answerLabel, evidenceSelection, formatDecimal } from '../utils/domain'
import {
  Button,
  Card,
  ErrorState,
  Field,
  PageHeader,
  QueryState,
  Select,
  StatusBadge,
  Textarea,
} from '../components/ui'
import { useToast } from '../components/ui/Toast'
import TranscriptViewer from '../components/conversations/TranscriptViewer'
import EvaluationPanel from '../components/evaluations/EvaluationPanel'
export function ReviewerDecision({ appeal, criterion, result, onSubmit, busy, error }) {
  const [decision, setDecision] = useState('upheld'),
    [answer, setAnswer] = useState(''),
    [reason, setReason] = useState('')
  const allowed =
    criterion?.criterion_type === 'scale' ? criterion.allowed_values.map(String) : ['yes', 'no']
  if (criterion?.allow_na) allowed.push('na')
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({
          decision,
          reason: reason.trim(),
          ...(decision === 'revised' ? { revised_answer: answer } : {}),
        })
      }}
    >
      <h2>Решение проверяющего</h2>
      <p>
        Текущий ответ: <strong>{answerLabel(result?.current_answer)}</strong>
      </p>
      <Field label="Решение">
        <Select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="upheld">Подтвердить оценку</option>
          <option value="revised">Изменить оценку</option>
        </Select>
      </Field>
      {decision === 'revised' && (
        <Field label="Новый ответ">
          <Select required value={answer} onChange={(e) => setAnswer(e.target.value)}>
            <option value="" disabled>
              Выберите допустимый ответ
            </option>
            {allowed.map((a) => (
              <option key={a} value={a}>
                {answerLabel(a)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="Причина решения">
        <Textarea
          required
          maxLength={10000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      {error && <ErrorState error={error} />}
      <Button
        type="submit"
        disabled={
          busy ||
          appeal.status !== 'pending' ||
          !criterion ||
          !reason.trim() ||
          (decision === 'revised' && (!answer || answer === String(result?.current_answer)))
        }
      >
        {busy ? 'Сохранение…' : 'Сохранить решение'}
      </Button>
    </form>
  )
}
export default function AppealDetail() {
  const { id } = useParams(),
    notify = useToast()
  const catalog = useVersionCatalog(),
    workspace = useWorkspace()
  const appeal = useQuery({
    queryKey: ['appeal', id],
    queryFn: ({ signal }) => getAppeal(id, signal),
  })
  const evaluation = useQuery({
    queryKey: ['evaluation', appeal.data?.evaluation_id],
    enabled: !!appeal.data,
    queryFn: ({ signal }) => getEvaluation(appeal.data.evaluation_id, signal),
  })
  const conversation = useQuery({
    queryKey: ['conversation', evaluation.data?.conversation_id],
    enabled: !!evaluation.data,
    queryFn: ({ signal }) => getConversation(evaluation.data.conversation_id, signal),
  })
  const version = catalog.data?.find((v) => v.id === evaluation.data?.checklist_version_id),
    result = evaluation.data?.results.find((r) => r.id === appeal.data?.criterion_result_id),
    criterion = version?.criteria.find((c) => c.id === result?.criterion_id)
  const [selection, setSelection] = useState(null),
    [error, setError] = useState(null)
  const action = useAction((payload) => decideAppeal(id, payload))
  function evidence(e) {
    try {
      const next = evidenceSelection(conversation.data.messages, e)
      setSelection(next)
      setError(null)
      requestAnimationFrame(() => {
        const el = document.getElementById(`message-${next.first}`)
        el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        el?.focus({ preventScroll: true })
      })
    } catch (err) {
      setError(err)
    }
  }
  return (
    <>
      <PageHeader
        title={`Апелляция #${id}`}
        description="Проверьте доказательства и сохраните обоснованное решение."
      >
        <Link className="button secondary" to="/appeals">
          Все апелляции
        </Link>
      </PageHeader>
      <QueryState query={appeal}>
        {appeal.data && (
          <>
            <Card>
              <div className="section-heading">
                <h2>Комментарий заявителя</h2>
                <StatusBadge status={appeal.data.status} />
              </div>
              <p className="preserve-text">{appeal.data.comment}</p>
              <Link to={`/evaluations/${appeal.data.evaluation_id}`}>
                Открыть всю оценку #{appeal.data.evaluation_id} →
              </Link>
            </Card>
            <QueryState query={evaluation}>
              <QueryState query={conversation}>
                <QueryState query={catalog}>
                  {result && conversation.data && (
                    <div className="conversation-grid">
                      <Card className="transcript-card">
                        <h2>Контекст разговора</h2>
                        {error && <ErrorState error={error} />}
                        <TranscriptViewer
                          messages={conversation.data.messages}
                          selection={selection}
                        />
                      </Card>
                      <div>
                        <Card>
                          {appeal.data.status === 'pending' ? (
                            <ReviewerDecision
                              appeal={appeal.data}
                              criterion={criterion}
                              result={result}
                              busy={action.isPending}
                              error={action.error}
                              onSubmit={async (payload) => {
                                try {
                                  await action.mutateAsync(payload)
                                  notify('Решение сохранено. Итог пересчитан backend.')
                                } catch {
                                  /* rendered */
                                }
                              }}
                            />
                          ) : (
                            <>
                              <h2>Решение сохранено</h2>
                              <p>{appeal.data.decision?.reason}</p>
                              <p>
                                {answerLabel(appeal.data.decision?.original_answer)} →{' '}
                                {answerLabel(appeal.data.decision?.revised_answer)}
                              </p>
                              <p>
                                Итог при решении:{' '}
                                {formatDecimal(appeal.data.decision?.original_final_score)} →{' '}
                                {formatDecimal(appeal.data.decision?.revised_final_score)}
                              </p>
                            </>
                          )}
                        </Card>
                        <Card>
                          <EvaluationPanel
                            evaluation={{
                              ...evaluation.data,
                              results: [result],
                            }}
                            version={version}
                            appeals={workspace.data?.appeals.filter(
                              (a) =>
                                a.evaluation_id === evaluation.data.id &&
                                a.criterion_result_id === result.id,
                            )}
                            onEvidence={evidence}
                          />
                        </Card>
                      </div>
                    </div>
                  )}
                </QueryState>
              </QueryState>
            </QueryState>
          </>
        )}
      </QueryState>
    </>
  )
}
