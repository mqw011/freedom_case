import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createAppeal } from '../../api/appeals'
import { useAction } from '../../hooks/data'
import { answerLabel, formatDecimal } from '../../utils/domain'
import { Button, ErrorState, Field, Modal, Textarea } from '../ui'
import { useToast } from '../ui/Toast'
export default function AppealForm({ evaluationId, result, criterion, onClose }) {
  const [comment, setComment] = useState('')
  const mutation = useAction((data) => createAppeal(evaluationId, data))
  const notify = useToast()
  const navigate = useNavigate()
  async function submit(e) {
    e.preventDefault()
    try {
      const a = await mutation.mutateAsync({
        criterion_result_id: result.id,
        comment: comment.trim(),
      })
      notify('Апелляция создана')
      onClose()
      navigate(`/appeals/${a.id}`)
    } catch {
      /* displayed */
    }
  }
  return (
    <Modal
      title={`Оспорить критерий ${criterion?.code || result.criterion_code}`}
      onClose={onClose}
      busy={mutation.isPending}
    >
      <form onSubmit={submit}>
        <h3>{criterion?.title}</h3>
        <p>
          Исходный ответ: <strong>{answerLabel(result.answer)}</strong> · Баллы:{' '}
          {formatDecimal(result.weighted_score)}
        </p>
        <p>{result.explanation}</p>
        {result.evidence.map((e) => (
          <blockquote key={e.id}>{e.excerpt || e.explanation}</blockquote>
        ))}
        <Field label="Причина несогласия">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            required
            maxLength={10000}
          />
        </Field>
        {mutation.error && <ErrorState error={mutation.error} />}
        <div className="modal-actions">
          <Button variant="secondary" disabled={mutation.isPending} onClick={onClose}>
            Назад
          </Button>
          <Button type="submit" disabled={mutation.isPending || !comment.trim()}>
            Подать апелляцию
          </Button>
        </div>
      </form>
    </Modal>
  )
}
