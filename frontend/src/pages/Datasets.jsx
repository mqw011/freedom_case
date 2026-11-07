import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Upload, Database } from 'lucide-react'
import { useAction, useWorkspace } from '../hooks/data'
import { importFile, importGroup } from '../api/datasets'
import {
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  PageHeader,
  QueryState,
  SectionHeader,
  Table,
  EmptyState,
} from '../components/ui'
import { dateLabel } from '../utils/domain'
export default function Datasets() {
  const query = useWorkspace()
  const [group, setGroup] = useState('')
  const [file, setFile] = useState(null)
  const [report, setReport] = useState(null)
  const action = useAction(({ kind, value }) =>
    kind === 'group' ? importGroup(value) : importFile(value),
  )
  async function submit(kind, value) {
    setReport(null)
    try {
      setReport(await action.mutateAsync({ kind, value }))
    } catch {
      /* displayed */
    }
  }
  return (
    <>
      <PageHeader
        title="Импорт данных"
        description="Новые и контрольные наборы без изменения кода. Подписанный адрес API остаётся на backend."
      />
      <div className="two-columns">
        <Card>
          <SectionHeader title="API организаторов">
            <Database size={20} />
          </SectionHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit('group', group)
            }}
          >
            <Field
              label="Group ID"
              hint="Латинские буквы, цифры, дефис или подчёркивание. До 64 символов."
            >
              <Input
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                required
                pattern="[A-Za-z0-9][A-Za-z0-9_\-]{0,63}"
                placeholder="Например, CONTROL"
              />
            </Field>
            <Button type="submit" disabled={action.isPending}>
              Импортировать по group_id
            </Button>
          </form>
        </Card>
        <Card>
          <SectionHeader title="Загрузить JSON">
            <Upload size={20} />
          </SectionHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (file) submit('file', file)
            }}
          >
            <Field
              label="JSON-файл набора"
              hint="Формат организаторов: error, isSuccess, data.records. До 20 МБ по умолчанию."
            >
              <Input
                type="file"
                accept=".json,application/json"
                required
                onChange={(e) => setFile(e.target.files[0] || null)}
              />
            </Field>
            <Button type="submit" disabled={action.isPending || !file}>
              Загрузить JSON
            </Button>
          </form>
        </Card>
      </div>
      {action.isPending && <p role="status">Импорт выполняется. Не закрывайте страницу…</p>}
      {action.error && <ErrorState error={action.error} />}
      {report && (
        <Card className="import-result">
          <h2>Набор {report.dataset.group_id} импортирован</h2>
          <div className="split-stat">
            <span>
              Получено <strong>{report.received_records}</strong>
            </span>
            <span>
              Добавлено <strong>{report.inserted}</strong>
            </span>
            <span>
              Пропущено <strong>{report.skipped}</strong>
            </span>
          </div>
          <p>Заявлено источником: {report.declared_records}</p>
          {report.warnings.map((w, i) => (
            <p className="notice" key={i}>
              {w}
            </p>
          ))}
          <Link className="button primary" to={`/conversations?dataset=${report.dataset.id}`}>
            Открыть набор и запустить batch
          </Link>
        </Card>
      )}
      <Card>
        <SectionHeader title="Импортированные наборы" />
        <QueryState query={query}>
          {query.data?.datasets.length ? (
            <Table
              caption="Наборы данных"
              headers={['Набор', 'Записей', 'Источник', 'Импортирован', '']}
            >
              {query.data.datasets.map((d) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.group_id}</strong>
                  </td>
                  <td>{d.total_records}</td>
                  <td>{d.source}</td>
                  <td>{dateLabel(d.imported_at)}</td>
                  <td>
                    <Link to={`/conversations?dataset=${d.id}`}>Диалоги →</Link>
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <EmptyState title="Наборы пока не импортированы" />
          )}
        </QueryState>
      </Card>
    </>
  )
}
