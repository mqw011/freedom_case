import { useEffect, useId, useRef, Children, cloneElement, isValidElement } from 'react'
import { X, AlertCircle, Inbox, ChevronLeft, ChevronRight } from 'lucide-react'
import { statusLabel, formatDecimal } from '../../utils/domain'
export function Button({ variant = 'primary', className = '', children, ...props }) {
  return (
    <button className={`button ${variant} ${className}`} type="button" {...props}>
      {children}
    </button>
  )
}
function labelControl(children, id, hintId) {
  return Children.map(children, (child) => {
    if (!isValidElement(child)) return child
    if ([Input, Select, Textarea, 'input', 'select', 'textarea'].includes(child.type))
      return cloneElement(child, { id, 'aria-describedby': hintId })
    return child.props.children
      ? cloneElement(child, {}, labelControl(child.props.children, id, hintId))
      : child
  })
}
export function Field({ label, children, hint }) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {typeof children === 'function'
        ? children(id)
        : labelControl(children, id, hint ? `${id}-hint` : undefined)}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  )
}
export function Input(props) {
  return <input className="input" {...props} />
}
export function Select(props) {
  return <select className="input" {...props} />
}
export function Textarea(props) {
  return <textarea className="input" rows={3} {...props} />
}
export function Badge({ children, tone = 'neutral' }) {
  return <span className={`badge ${tone}`}>{children}</span>
}
export function StatusBadge({ status }) {
  return <Badge tone={status}>{statusLabel(status)}</Badge>
}
export function Card({ children, className = '', ...props }) {
  return (
    <section className={`card ${className}`} {...props}>
      {children}
    </section>
  )
}
export function PageHeader({ eyebrow, title, description, children }) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow || 'CONVERSATION QUALITY ANALYTICS'}</p>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      <div className="actions">{children}</div>
    </div>
  )
}
export function SectionHeader({ title, children }) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {children}
    </div>
  )
}
export function EmptyState({ title = 'Нет данных', children }) {
  return (
    <div className="empty">
      <Inbox size={28} aria-hidden="true" />
      <h3>{title}</h3>
      {children}
    </div>
  )
}
export function ErrorState({ error, retry }) {
  return (
    <div className="notice danger" role="alert">
      <AlertCircle size={19} aria-hidden="true" />
      <div>
        <strong>{error?.message || 'Не удалось загрузить данные'}</strong>
        {error?.code && <small>Код: {error.code}</small>}
        {(Array.isArray(error?.details) ? error.details : [])?.map((d, i) => (
          <small key={i}>
            {d.loc?.join(' → ')}: {d.message}
          </small>
        ))}
        {retry && (
          <Button variant="secondary" onClick={retry}>
            Повторить
          </Button>
        )}
      </div>
    </div>
  )
}
export function Skeleton() {
  return <div className="skeleton" aria-hidden="true" />
}
export function LoadingState() {
  return (
    <div role="status" aria-label="Загрузка данных">
      <p className="muted">Загрузка данных…</p>
      <Skeleton />
      <Skeleton />
      <Skeleton />
    </div>
  )
}
export function QueryState({ query, children }) {
  if (query.isPending) return <LoadingState />
  if (query.isError && !query.data) return <ErrorState error={query.error} retry={query.refetch} />
  return (
    <>
      {query.isError && <ErrorState error={query.error} retry={query.refetch} />} {children}
    </>
  )
}
export function Table({ headers, children, caption }) {
  return (
    <div className="table-scroll" role="region" aria-label={caption} tabIndex={0}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={i} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
export function Pagination({ page, pages, total, onChange }) {
  return (
    <nav className="pagination" aria-label="Пагинация">
      <span>
        {total} записей · страница {page} из {pages}
      </span>
      <div className="actions">
        <Button
          variant="secondary"
          aria-label="Предыдущая страница"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft size={16} />
        </Button>
        <Button
          variant="secondary"
          aria-label="Следующая страница"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </nav>
  )
}
export function ProgressBar({ value }) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label="Доля завершившихся заданий"
      aria-valuenow={Number(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${Math.max(0, Math.min(100, Number(value)))}%` }} />
    </div>
  )
}
export function Tabs({ value, onChange, options }) {
  return (
    <div className="tabs" role="tablist">
      {options.map(([id, label]) => (
        <button
          type="button"
          role="tab"
          tabIndex={id === value ? 0 : -1}
          onKeyDown={(e) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
            e.preventDefault()
            const index = options.findIndex(([key]) => key === id)
            const next =
              e.key === 'Home'
                ? 0
                : e.key === 'End'
                  ? options.length - 1
                  : (index + (e.key === 'ArrowRight' ? 1 : -1) + options.length) % options.length
            onChange(options[next][0])
            e.currentTarget.parentElement.children[next].focus()
          }}
          aria-selected={id === value}
          key={id}
          onClick={() => onChange(id)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
export function Tooltip({ text, children }) {
  return (
    <span className="tooltip" tabIndex={0}>
      {children}
      <span role="tooltip">{text}</span>
    </span>
  )
}
export function Modal({ title, children, onClose, busy = false }) {
  const ref = useRef()
  const id = useId()
  useEffect(() => {
    const dialog = ref.current
    const previous = document.activeElement
    dialog.showModal()
    return () => {
      dialog.close()
      previous?.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={id}
      onCancel={(e) => {
        e.preventDefault()
        if (!busy) onClose()
      }}
    >
      <div className="modal-heading">
        <h2 id={id}>{title}</h2>
        <Button variant="ghost" aria-label="Закрыть диалог" disabled={busy} onClick={onClose}>
          <X size={20} />
        </Button>
      </div>
      {children}
    </dialog>
  )
}
export function ConfirmDialog({ title, children, onConfirm, onClose, busy, error }) {
  return (
    <Modal title={title} onClose={onClose} busy={busy}>
      <p>{children}</p>
      {error && <ErrorState error={error} />}
      <div className="modal-actions">
        <Button variant="secondary" disabled={busy} onClick={onClose}>
          Назад
        </Button>
        <Button disabled={busy} onClick={onConfirm}>
          {busy ? 'Сохранение…' : 'Подтвердить'}
        </Button>
      </div>
    </Modal>
  )
}
export function Score({ value, large = false }) {
  return (
    <span className={`score ${large ? 'large' : ''}`}>
      {formatDecimal(value)}
      {large && value !== null && <small>/ 100</small>}
    </span>
  )
}
