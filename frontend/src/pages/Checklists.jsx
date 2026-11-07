import { useState } from 'react'
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, ArrowUp, ArrowDown, Trash2, Pencil, CheckCircle } from 'lucide-react'
import { activateVersion, createChecklist, createVersion, getVersions } from '../api/checklists'
import { useAction, useWorkspace } from '../hooks/data'
import {
  newCriterion,
  readConfig,
  validateChecklist,
  weightTotal,
  formatDecimal,
} from '../utils/domain'
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  QueryState,
  Select,
  Textarea,
} from '../components/ui'
import { useToast } from '../components/ui/Toast'
export function CriterionEditor({ criterion: c, index, onChange, onRemove, onMove, count }) {
  const update = (key, value) => onChange({ ...c, [key]: value })
  function type(value) {
    onChange({
      ...c,
      criterion_type: value,
      ...(value !== 'scale'
        ? { allowed_values: ['0', '1'], max_score: '1', scale_labels: {} }
        : {}),
      ...(value === 'flag'
        ? { weight: '0', allow_na: false, na_condition: null }
        : c.criterion_type === 'flag'
          ? { weight: '10' }
          : {}),
    })
  }
  return (
    <details className="editor-criterion" open>
      <summary>
        <span className="criterion-number">{c.code || index + 1}</span>
        <strong>{c.title || 'Новый критерий'}</strong>
        <Badge>{c.criterion_type}</Badge>
      </summary>
      <div className="editor-body">
        <div className="actions editor-actions">
          <Button
            variant="ghost"
            aria-label={`Поднять критерий ${index + 1}`}
            disabled={index === 0}
            onClick={() => onMove(index, -1)}
          >
            <ArrowUp size={16} />
          </Button>
          <Button
            variant="ghost"
            aria-label={`Опустить критерий ${index + 1}`}
            disabled={index === count - 1}
            onClick={() => onMove(index, 1)}
          >
            <ArrowDown size={16} />
          </Button>
          <Button variant="danger" onClick={onRemove}>
            <Trash2 size={15} />
            Удалить критерий
          </Button>
        </div>
        <div className="form-grid">
          <Field label="Код">
            <Input value={c.code} maxLength={40} onChange={(e) => update('code', e.target.value)} />
          </Field>
          <Field label="Название">
            <Input
              value={c.title}
              maxLength={300}
              onChange={(e) => update('title', e.target.value)}
            />
          </Field>
          <Field label="Секция">
            <Input
              value={c.section}
              maxLength={300}
              onChange={(e) => update('section', e.target.value)}
            />
          </Field>
          <Field label="Тип">
            <Select value={c.criterion_type} onChange={(e) => type(e.target.value)}>
              <option value="binary">Да / Нет</option>
              <option value="scale">Числовая шкала</option>
              <option value="flag">Флаг нарушения</option>
            </Select>
          </Field>
          <Field label="Вес">
            <Input
              inputMode="decimal"
              value={c.weight}
              disabled={c.criterion_type === 'flag'}
              onChange={(e) => update('weight', e.target.value)}
            />
          </Field>
          <Field label="Порядок отображения">
            <Input
              type="number"
              min="0"
              step="1"
              value={c.display_order}
              onChange={(e) => update('display_order', Number(e.target.value))}
            />
          </Field>
        </div>
        <Field label="Описание критерия">
          <Textarea
            value={c.description}
            maxLength={10000}
            onChange={(e) => update('description', e.target.value)}
          />
        </Field>
        {c.criterion_type === 'scale' && (
          <>
            <div className="form-grid">
              <Field
                label="Допустимые ступени"
                hint="Через запятую. Десятичный разделитель — точка."
              >
                <Input
                  value={c.allowed_values.join(',')}
                  onChange={(e) => {
                    const values = e.target.value.split(',').map((v) => v.trim())
                    onChange({
                      ...c,
                      allowed_values: values,
                      scale_labels: Object.fromEntries(
                        Object.entries(c.scale_labels).filter(([key]) => values.includes(key)),
                      ),
                    })
                  }}
                />
              </Field>
              <Field label="Максимум шкалы">
                <Input
                  value={c.max_score}
                  inputMode="decimal"
                  onChange={(e) => update('max_score', e.target.value)}
                />
              </Field>
            </div>
            <div className="form-grid">
              {[...new Set(c.allowed_values)].filter(Boolean).map((value) => (
                <Field key={value} label={`Описание ступени ${value}`}>
                  <Textarea
                    value={c.scale_labels[value] || ''}
                    maxLength={10000}
                    onChange={(e) => {
                      const labels = { ...c.scale_labels }
                      if (e.target.value.trim()) labels[value] = e.target.value
                      else delete labels[value]
                      update('scale_labels', labels)
                    }}
                  />
                </Field>
              ))}
            </div>
          </>
        )}
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={c.allow_na}
            disabled={c.criterion_type === 'flag'}
            onChange={(e) =>
              onChange({
                ...c,
                allow_na: e.target.checked,
                na_condition: e.target.checked ? '' : null,
              })
            }
          />
          Разрешить N/A
        </label>
        {c.allow_na && (
          <Field label="Условие N/A">
            <Textarea
              value={c.na_condition || ''}
              maxLength={10000}
              onChange={(e) => update('na_condition', e.target.value)}
            />
          </Field>
        )}
      </div>
    </details>
  )
}
export default function Checklists() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const workspace = useWorkspace()
  const navigate = useNavigate(),
    notify = useToast()
  const [draft, setDraft] = useState(null),
    [name, setName] = useState(''),
    [description, setDescription] = useState(''),
    [confirm, setConfirm] = useState(null)
  const checklist = workspace.data?.checklists.find((c) => c.id === Number(id))
  const versions = useQuery({
    queryKey: ['versions', Number(id)],
    queryFn: ({ signal }) => getVersions(id, signal),
    enabled: !!id,
  })
  const version =
    versions.data?.find(
      (v) => v.id === Number(params.get('version') || checklist?.active_version_id),
    ) || versions.data?.at(-1)
  const save = useAction((criteria) =>
    id
      ? createVersion(Number(id), criteria)
      : createChecklist({
          name: name.trim(),
          description: description.trim(),
          version: { criteria },
        }),
  )
  const activation = useAction((v) => activateVersion(Number(id), v))
  const total = draft ? weightTotal(draft) : version && weightTotal(version.criteria)
  const errors = draft
    ? [
        ...validateChecklist(draft.filter((c) => !c._labelsInvalid)),
        ...(draft.some((c) => c._labelsInvalid) ? ['Исправьте JSON описаний шкалы.'] : []),
      ]
    : []
  function edit() {
    setDraft(
      version.criteria.map((c) => ({
        ...readConfig(c),
        allowed_values: c.allowed_values.map(String),
      })),
    )
  }
  function move(index, delta) {
    const next = [...draft]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    setDraft(next.map((c, i) => ({ ...c, display_order: i })))
  }
  async function submit(e) {
    e.preventDefault()
    if (errors.length) return
    try {
      const result = await save.mutateAsync(draft.map(readConfig))
      setDraft(null)
      notify('Новая версия сохранена')
      if (id) setParams({ version: result.id })
      else navigate(`/checklists/${result.id}`)
    } catch {
      /* rendered */
    }
  }
  return (
    <>
      <PageHeader
        title={id ? checklist?.name || 'Чек-лист' : 'Чек-листы'}
        description="Критерии меняются через версии. Старые оценки и доказательства сохраняются."
      >
        {id ? (
          <Link className="button secondary" to="/checklists">
            Все чек-листы
          </Link>
        ) : (
          <Button
            onClick={() => {
              setDraft([newCriterion(0)])
              setName('')
              setDescription('')
            }}
          >
            <Plus size={17} />
            Создать чек-лист
          </Button>
        )}
      </PageHeader>
      <QueryState query={workspace}>
        {!id &&
          !draft &&
          (workspace.data?.checklists.length ? (
            <div className="checklist-grid">
              {workspace.data.checklists.map((c) => (
                <Card key={c.id}>
                  <Badge>Активная версия ID {c.active_version_id || '—'}</Badge>
                  <h2>{c.name}</h2>
                  <p>{c.description}</p>
                  <Link className="button secondary" to={`/checklists/${c.id}`}>
                    Открыть редактор →
                  </Link>
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState title="Чек-листов пока нет" />
          ))}
      </QueryState>
      {id && !draft && (
        <QueryState query={versions}>
          {version && (
            <>
              <div className="editor-toolbar">
                <Field label="История версий">
                  <Select
                    value={version.id}
                    onChange={(e) => setParams({ version: e.target.value })}
                  >
                    {versions.data.map((v) => (
                      <option key={v.id} value={v.id}>
                        Версия {v.version_number} · ID {v.id}
                        {v.id === checklist?.active_version_id ? ' · Активна' : ''}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Badge tone={total === '100' ? 'completed' : 'failed'}>
                  Total Weight: {total} / 100
                </Badge>
                <Button onClick={edit}>
                  <Pencil size={16} />
                  Создать новую версию
                </Button>
                <Button
                  variant="secondary"
                  disabled={total !== '100' || version.id === checklist?.active_version_id}
                  onClick={() => setConfirm(version.id)}
                >
                  <CheckCircle size={16} />
                  Активировать
                </Button>
                <Link className="text-link" to={`/conversations?checklist_id=${id}`}>
                  Выбрать диалоги для переоценки →
                </Link>
              </div>
              <div className="notice">
                Сохранённая версия неизменяема. Редактирование создаст отдельную копию.
              </div>
              {version.criteria.map((c) => (
                <Card key={c.id} className="criterion-preview">
                  <div className="section-heading">
                    <h2>
                      {c.code} · {c.title}
                    </h2>
                    <Badge>Вес {formatDecimal(c.weight)}</Badge>
                  </div>
                  <p className="muted">
                    {c.section} · {c.criterion_type}
                  </p>
                  <p>{c.description}</p>
                  <p>
                    Шкала: {c.allowed_values.join(' / ')} · Максимум: {c.max_score}
                  </p>
                  {Object.entries(c.scale_labels).map(([v, label]) => (
                    <p key={v}>
                      <strong>{v}</strong> — {label}
                    </p>
                  ))}
                  {c.allow_na && <p className="na-condition">N/A: {c.na_condition}</p>}
                </Card>
              ))}
            </>
          )}
        </QueryState>
      )}
      {draft && (
        <form onSubmit={submit}>
          <div className="editor-toolbar sticky">
            <h2>{id ? 'Новая версия' : 'Новый чек-лист'}</h2>
            <Badge tone={total === '100' ? 'completed' : 'failed'}>
              Total Weight: {total ?? '—'} / 100
            </Badge>
            <Button variant="secondary" disabled={save.isPending} onClick={() => setDraft(null)}>
              Отменить изменения
            </Button>
            <Button
              type="submit"
              disabled={
                save.isPending ||
                !!errors.length ||
                (!id && (total !== '100' || !name.trim() || !description.trim()))
              }
            >
              Сохранить {id ? 'версию' : 'чек-лист'}
            </Button>
          </div>
          {!id && (
            <Card>
              <Field label="Название чек-листа">
                <Input
                  required
                  maxLength={300}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              <Field label="Описание чек-листа">
                <Textarea
                  required
                  maxLength={10000}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </Field>
            </Card>
          )}
          {total !== '100' && (
            <div className="notice">
              Сумма весов не 100.{' '}
              {id
                ? 'Версию можно сохранить, но нельзя активировать.'
                : 'Для создания активного чек-листа нужна сумма 100.'}
            </div>
          )}
          {!!errors.length && (
            <div className="notice danger" role="alert">
              <ul>
                {errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
          {save.error && <ErrorState error={save.error} />}
          {draft.map((c, i) => (
            <CriterionEditor
              key={i}
              criterion={c}
              index={i}
              count={draft.length}
              onChange={(value) => setDraft((d) => d.map((v, n) => (n === i ? value : v)))}
              onRemove={() => setDraft((d) => d.filter((_, n) => n !== i))}
              onMove={move}
            />
          ))}
          <Button
            variant="secondary"
            disabled={draft.length >= 100}
            onClick={() =>
              setDraft((d) => [
                ...d,
                newCriterion(Math.max(-1, ...d.map((c) => c.display_order)) + 1),
              ])
            }
          >
            <Plus size={17} />
            Добавить критерий
          </Button>
        </form>
      )}
      {confirm && (
        <ConfirmDialog
          title="Активировать версию?"
          onClose={() => setConfirm(null)}
          busy={activation.isPending}
          error={activation.error}
          onConfirm={async () => {
            try {
              await activation.mutateAsync(confirm)
              notify('Версия активирована')
              setConfirm(null)
            } catch {
              /* rendered */
            }
          }}
        >
          Новые AI задания получат версию ID {confirm}. Исходные оценки не изменятся.
        </ConfirmDialog>
      )}
    </>
  )
}
