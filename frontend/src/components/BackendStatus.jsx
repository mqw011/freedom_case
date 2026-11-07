import { useHealth } from '../hooks/data'
import { Badge } from './ui'
export default function BackendStatus() {
  const { backend, ai } = useHealth()
  return (
    <div className="health" aria-live="polite" aria-label="Состояние сервисов">
      <span>
        Backend{' '}
        <Badge tone={backend.isSuccess ? 'completed' : backend.isPending ? 'queued' : 'failed'}>
          {backend.isPending ? 'Проверка' : backend.isSuccess ? 'Online' : 'Offline'}
        </Badge>
      </span>
      <span>
        LLM provider{' '}
        <Badge tone={!ai.isError && ai.data?.provider.available ? 'completed' : 'failed'}>
          {ai.isPending
            ? 'Проверка'
            : ai.isError
              ? 'Статус неизвестен'
              : !ai.isError && ai.data?.provider.available
                ? 'Доступен'
                : 'Недоступен'}
        </Badge>
      </span>
      <span>
        AI Worker{' '}
        <Badge tone={!ai.isError && ai.data?.worker.available ? 'completed' : 'neutral'}>
          {ai.isPending
            ? 'Проверка'
            : ai.isError
              ? 'Статус неизвестен'
              : !ai.isError && ai.data?.worker.available
                ? 'Online'
                : 'Offline'}
        </Badge>
      </span>
    </div>
  )
}
