import { Link } from 'react-router-dom'
import { ProgressBar, StatusBadge } from '../ui'
import { formatDecimal } from '../../utils/domain'
export default function BatchCard({ batch }) {
  return (
    <div className="batch-summary">
      <div className="section-heading">
        <h3>
          <Link to={`/ai-batches/${batch.id}`}>Пакет #{batch.id}</Link>
        </h3>
        <strong>{formatDecimal(batch.percentage)}%</strong>
      </div>
      <ProgressBar value={batch.percentage} />
      <p>
        Всего {batch.total} · Версия ID {batch.checklist_version_id}
      </p>
      <div className="batch-counts">
        {['queued', 'running', 'completed', 'failed', 'cancelled'].map((s) => (
          <span key={s}>
            <StatusBadge status={s} /> <strong>{batch[s]}</strong>
          </span>
        ))}
      </div>
      <small>
        Прогресс включает ошибки и отмены. Успешных оценок: {batch.completed} из {batch.total}.
      </small>
    </div>
  )
}
