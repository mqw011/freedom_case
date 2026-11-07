import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAction, useHealth, useVersionCatalog, useWorkspace } from '../../hooks/data'
import { createAIBatch, createAIJob } from '../../api/ai'
import { Button, ErrorState, Field, Modal, Select } from '../ui'
import { useToast } from '../ui/Toast'
import { weightTotal } from '../../utils/domain'
export default function AIStartDialog({ ids, onClose, checklistId }) {
  const { data } = useWorkspace()
  const catalog = useVersionCatalog()
  const { ai } = useHealth()
  const [checklist, setChecklist] = useState(String(checklistId || data?.checklists[0]?.id || ''))
  const [version, setVersion] = useState('')
  const keys = useRef(new Map())
  const navigate = useNavigate()
  const notify = useToast()
  const mutation = useAction((payload) =>
    ids.length === 1 ? createAIJob(payload) : createAIBatch(payload),
  )
  const selected = data?.checklists.find((c) => c.id === Number(checklist))
  async function submit(e) {
    e.preventDefault()
    const payload = {
      ...(ids.length === 1 ? { conversation_id: ids[0] } : { conversation_ids: ids }),
      checklist_id: Number(checklist),
      checklist_version_id: version ? Number(version) : null,
    }
    const hash = JSON.stringify(payload)
    if (!keys.current.has(hash)) keys.current.set(hash, crypto.randomUUID())
    try {
      const result = await mutation.mutateAsync({
        ...payload,
        idempotency_key: keys.current.get(hash),
      })
      notify(`${ids.length} диалогов поставлено в очередь`)
      onClose()
      navigate(ids.length === 1 ? `/ai-jobs/${result.id}` : `/ai-batches/${result.id}`)
    } catch {
      /* Error is rendered below. */
    }
  }
  return (
    <Modal
      title={ids.length === 1 ? 'Запустить AI-оценку' : 'Пакетная оценка'}
      onClose={onClose}
      busy={mutation.isPending}
    >
      <form onSubmit={submit}>
        <p>
          Выбрано диалогов: <strong>{ids.length}</strong>. Версия закрепится при постановке задания.
        </p>
        {(!ai.data?.provider.available || !ai.data?.worker.available) && (
          <div className="notice">
            {!ai.data?.provider.available && 'LLM provider недоступен. '}
            {!ai.data?.worker.available && 'AI Worker offline. '}Задания сохранятся в очереди.
            Результат появится только после реальной обработки.
          </div>
        )}
        <Field label="Чек-лист">
          <Select
            value={checklist}
            required
            onChange={(e) => {
              setChecklist(e.target.value)
              setVersion('')
            }}
          >
            {data?.checklists.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Версия для оценки">
          <Select value={version} onChange={(e) => setVersion(e.target.value)}>
            <option value="">Активная версия · ID {selected?.active_version_id || '—'}</option>
            {catalog.data
              ?.filter((v) => v.checklist_id === Number(checklist))
              .map((v) => (
                <option key={v.id} value={v.id} disabled={weightTotal(v.criteria) !== '100'}>
                  Версия {v.version_number} · ID {v.id}
                  {weightTotal(v.criteria) !== '100' ? ' · сумма весов не 100' : ''}
                </option>
              ))}
          </Select>
        </Field>
        {catalog.isError && <ErrorState error={catalog.error} retry={catalog.refetch} />}
        {mutation.error && <ErrorState error={mutation.error} />}
        <div className="modal-actions">
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            Назад
          </Button>
          <Button
            type="submit"
            disabled={mutation.isPending || !selected || (!version && !selected.active_version_id)}
          >
            {mutation.isPending ? 'Постановка…' : 'Поставить в очередь'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
