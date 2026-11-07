import { useState } from 'react'
import { Link } from 'react-router-dom'
import { cancelAIJob, retryAIJob } from '../../api/ai'
import { useAction } from '../../hooks/data'
import { Button, ConfirmDialog } from '../ui'
import { useToast } from '../ui/Toast'
export default function JobActions({ job }) {
  const [confirm, setConfirm] = useState(null),
    notify = useToast()
  const action = useAction((kind) => (kind === 'retry' ? retryAIJob(job.id) : cancelAIJob(job.id)))
  return (
    <div className="actions">
      {job.status === 'failed' && (
        <Button variant="secondary" onClick={() => setConfirm('retry')}>
          Повторить
        </Button>
      )}
      {['queued', 'running'].includes(job.status) && (
        <Button
          variant="secondary"
          disabled={job.cancel_requested}
          onClick={() => setConfirm('cancel')}
        >
          {job.cancel_requested ? 'Отмена запрошена' : 'Отменить задание'}
        </Button>
      )}
      {job.evaluation_id && (
        <Link className="button secondary" to={`/evaluations/${job.evaluation_id}`}>
          Открыть оценку
        </Link>
      )}
      {confirm && (
        <ConfirmDialog
          title={confirm === 'retry' ? 'Повторить задание?' : 'Отменить задание?'}
          onClose={() => setConfirm(null)}
          busy={action.isPending}
          error={action.error}
          onConfirm={async () => {
            try {
              await action.mutateAsync(confirm)
              setConfirm(null)
              notify('Состояние задания обновлено')
            } catch {
              /* rendered */
            }
          }}
        >
          {confirm === 'retry'
            ? 'Сохранится история попыток и закреплённая версия чек-листа.'
            : 'У выполняющегося задания отмена подтверждается worker. Успешный результат отменённой задачи не сохраняется.'}
        </ConfirmDialog>
      )}
    </div>
  )
}
