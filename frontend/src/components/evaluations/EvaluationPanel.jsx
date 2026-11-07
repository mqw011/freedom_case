import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownLeft, Flag } from 'lucide-react'
import { answerLabel, formatDecimal } from '../../utils/domain'
import { Badge, Button, Score } from '../ui'
import AppealForm from '../appeals/AppealForm'
export default function EvaluationPanel({ evaluation, version, job, appeals = [], onEvidence }) {
  const [appeal, setAppeal] = useState(null)
  return (
    <div className="evaluation-panel">
      <div className="evaluation-summary">
        <div className="actions">
          <Badge>
            {evaluation.source === 'ai'
              ? 'AI'
              : evaluation.source === 'test'
                ? 'Тестовая оценка'
                : 'Ручная оценка'}
          </Badge>
          <Badge>
            Версия {version?.version_number || '—'} · ID {evaluation.checklist_version_id}
          </Badge>
        </div>
        <Score value={evaluation.final_score} large />
        <p>Финальный балл · оценка #{evaluation.id}</p>
        <div className="split-stat">
          <span>
            Первоначальный <strong>{formatDecimal(evaluation.initial_score)}</strong>
          </span>
          <span>
            После пересмотра <strong>{formatDecimal(evaluation.final_score)}</strong>
          </span>
        </div>
        <p className={evaluation.critical_violation ? 'critical-flag' : 'muted'}>
          <Flag size={16} />
          {evaluation.critical_violation
            ? 'Грубое нарушение подтверждено'
            : 'Грубые нарушения не отмечены'}
        </p>
      </div>
      {job?.diagnostics?.needs_human_review && (
        <div className="notice">Требуется проверка человеком: модель указала неопределённость.</div>
      )}
      {job?.diagnostics?.review_codes?.map((code) => (
        <p className="notice" key={code}>
          {code === 'voice_transcript_only'
            ? 'Проанализирован только текст звонка.'
            : code.startsWith('external_fact_unverified')
              ? 'Фактическая корректность требует внешней проверки.'
              : `Примечание проверки: ${code}`}
        </p>
      ))}
      <div className="criterion-list">
        {evaluation.results.map((result) => {
          const c = version?.criteria.find((v) => v.id === result.criterion_id)
          return (
            <details className="criterion-result" key={result.id} open>
              <summary>
                <span className="criterion-number">{result.criterion_code}</span>
                <span>
                  {c?.title || `Критерий ${result.criterion_code}`}
                  <small>
                    Вес {formatDecimal(c?.weight)} · {c?.section}
                  </small>
                </span>
                <Badge
                  tone={
                    result.current_is_na
                      ? 'neutral'
                      : (
                            c?.criterion_type === 'flag'
                              ? result.current_answer === 'yes'
                              : result.current_answer === 'no'
                          )
                        ? 'failed'
                        : 'completed'
                  }
                >
                  {answerLabel(result.current_answer)}
                </Badge>
              </summary>
              <div className="criterion-body">
                <div className="split-stat">
                  <span>
                    Текущий вклад{' '}
                    <strong>
                      {result.current_is_na ? 'N/A' : formatDecimal(result.current_weighted_score)}
                    </strong>
                  </span>
                  <span>
                    Исходный ответ <strong>{answerLabel(result.answer)}</strong>
                  </span>
                </div>
                <p>{result.explanation}</p>
                {result.current_answer !== result.answer && (
                  <p className="notice">
                    Ответ пересмотрен. Обоснование и evidence выше относятся к исходной оценке;
                    причина изменения — в истории апелляций.
                  </p>
                )}
                {result.current_is_na && (
                  <p className="na-condition">
                    <strong>Условие N/A:</strong> {c?.na_condition || 'Описание версии недоступно'}
                  </p>
                )}
                <div className="evidence-list">
                  {result.evidence.length ? (
                    result.evidence.map((e) => (
                      <button
                        className="evidence"
                        key={e.id}
                        type="button"
                        onClick={() => onEvidence(e)}
                      >
                        <span>
                          <ArrowDownLeft size={16} />{' '}
                          {e.evidence_type === 'quote'
                            ? 'Цитата'
                            : e.evidence_type === 'range'
                              ? 'Диапазон'
                              : 'Отсутствующее действие'}{' '}
                          {e.message_id ? `· #${e.message_id}` : '· весь диалог'}
                        </span>
                        {e.excerpt && <q>{e.excerpt}</q>}
                        <small>{e.explanation}</small>
                      </button>
                    ))
                  ) : (
                    <p className="muted">Evidence не предоставлено.</p>
                  )}
                </div>
                <Button variant="secondary" onClick={() => setAppeal({ result, criterion: c })}>
                  Оспорить оценку
                </Button>
              </div>
            </details>
          )
        })}
      </div>
      <section className="appeal-history">
        <h3>История пересмотров</h3>
        {appeals.length ? (
          appeals.map((a) => (
            <div key={a.id}>
              <Link to={`/appeals/${a.id}`}>Апелляция #{a.id}</Link>
              <p>
                {a.decision
                  ? `${answerLabel(a.decision.original_answer)} → ${answerLabel(a.decision.revised_answer)} · ${a.decision.reason}`
                  : 'Ожидает решения'}
              </p>
            </div>
          ))
        ) : (
          <p className="muted">Пересмотров пока нет.</p>
        )}
      </section>
      {appeal && (
        <AppealForm evaluationId={evaluation.id} {...appeal} onClose={() => setAppeal(null)} />
      )}
    </div>
  )
}
