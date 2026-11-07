import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  MessagesSquare,
  CheckCheck,
  Gauge,
  ShieldAlert,
  Scale,
  Activity,
  CircleX,
  CircleCheck,
} from 'lucide-react'
import { useWorkspace } from '../hooks/data'
import { aggregate, channelLabel, dateLabel, formatDecimal } from '../utils/domain'
import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  QueryState,
  Score,
  SectionHeader,
  StatusBadge,
  Table,
} from '../components/ui'
function Bars({ items, total }) {
  return (
    <div className="bars">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span>{item.label}</span>
          <div className="bar-track">
            <i style={{ width: `${total ? (item.count / total) * 100 : 0}%` }} />
          </div>
          <strong>{item.count}</strong>
        </div>
      ))}
    </div>
  )
}
export default function Dashboard() {
  const query = useWorkspace()
  const data = query.data
  const stats = data && aggregate(data)
  const kpis = data && [
    ['Всего диалогов', data.conversations.length, MessagesSquare],
    ['Оценено диалогов', stats.latest.length, CheckCheck],
    ['Средний балл', formatDecimal(stats.average), Gauge],
    ['Грубые нарушения', stats.critical, ShieldAlert],
    ['Ожидают апелляции', data.appeals.filter((a) => a.status === 'pending').length, Scale],
    ['AI выполняется', data.jobs.filter((j) => j.status === 'running').length, Activity],
    ['AI ошибки', data.jobs.filter((j) => j.status === 'failed').length, CircleX],
    ['AI завершено', data.jobs.filter((j) => j.status === 'completed').length, CircleCheck],
  ]
  return (
    <>
      <PageHeader
        title="Обзор качества"
        description="От диалога к понятной оценке и проверяемым решениям."
      >
        <Link className="button secondary" to="/datasets">
          Импортировать данные
        </Link>
        <Link className="button primary" to="/conversations">
          Открыть диалоги <ArrowUpRight size={17} />
        </Link>
      </PageHeader>
      <QueryState query={query}>
        {data && (
          <>
            <div className="kpi-grid">
              {kpis.map(([label, value, Icon], i) => (
                <Card key={label} className={`kpi ${i === 2 ? 'accent-card' : ''}`}>
                  <div>
                    <span>{label}</span>
                    <Icon size={19} />
                  </div>
                  <strong>{value}</strong>
                  <small>
                    {i === 2
                      ? 'Последняя оценка · final_score'
                      : i === 3
                        ? 'Отдельный флаг, без обнуления балла'
                        : 'По данным рабочего пространства'}
                  </small>
                </Card>
              ))}
            </div>
            <p className="methodology">
              Методика: последняя завершённая оценка каждого диалога, финальный балл после
              апелляций. Null исключены: {stats.excluded}. Failed и cancelled задания не считаются
              оценками.
            </p>
            <div className="dashboard-grid">
              <Card>
                <SectionHeader title="Распределение качества">
                  <Badge>По диалогам</Badge>
                </SectionHeader>
                {stats.latest.length ? (
                  <Bars items={stats.distribution} total={stats.latest.length - stats.excluded} />
                ) : (
                  <EmptyState title="Оценок пока нет">
                    Выберите диалог и запустите оценку.
                  </EmptyState>
                )}
                <Link className="text-link" to="/conversations?critical=yes">
                  Диалоги с грубыми нарушениями <ArrowUpRight size={15} />
                </Link>
              </Card>
              <Card>
                <SectionHeader title="Языки и каналы" />
                <Bars items={stats.languages} total={data.conversations.length} />
                <div className="split-stat">
                  {['agent chat', 'voice call'].map((c) => (
                    <span key={c}>
                      {channelLabel(c)}{' '}
                      <strong>{data.conversations.filter((v) => v.channel === c).length}</strong>
                    </span>
                  ))}
                </div>
              </Card>
              <Card>
                <SectionHeader title="Очередь AI">
                  <Link to="/ai-jobs">Все задания →</Link>
                </SectionHeader>
                <div className="status-list">
                  {['queued', 'running', 'completed', 'failed', 'cancelled'].map((s) => (
                    <div key={s}>
                      <StatusBadge status={s} />
                      <strong>{data.jobs.filter((j) => j.status === s).length}</strong>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
            <div className="two-columns">
              <Card>
                <SectionHeader title="Последние оценки">
                  <Link to="/conversations?evaluated=yes">Все оценки →</Link>
                </SectionHeader>
                {stats.latest.length ? (
                  <Table caption="Последние оценки" headers={['Диалог', 'Источник', 'Итог', '']}>
                    {[...stats.latest]
                      .sort((a, b) => b.id - a.id)
                      .slice(0, 5)
                      .map((e) => (
                        <tr key={e.id}>
                          <td>
                            <Link to={`/conversations/${e.conversation_id}`}>
                              {data.conversations.find((c) => c.id === e.conversation_id)
                                ?.conversation_id || `#${e.conversation_id}`}
                            </Link>
                            <small>{dateLabel(e.completed_at)}</small>
                          </td>
                          <td>
                            <Badge>{e.source}</Badge>
                          </td>
                          <td>
                            <Score value={e.final_score} />
                            {e.critical_violation && <Badge tone="failed">Нарушение</Badge>}
                          </td>
                          <td>
                            <Link to={`/evaluations/${e.id}`} aria-label={`Открыть оценку ${e.id}`}>
                              <ArrowUpRight size={18} />
                            </Link>
                          </td>
                        </tr>
                      ))}
                  </Table>
                ) : (
                  <EmptyState title="Нет завершённых оценок" />
                )}
              </Card>
              <Card>
                <SectionHeader title="Последние апелляции">
                  <Link to="/appeals">Все апелляции →</Link>
                </SectionHeader>
                {data.appeals.length ? (
                  <div className="activity-list">
                    {[...data.appeals]
                      .reverse()
                      .slice(0, 5)
                      .map((a) => (
                        <Link key={a.id} to={`/appeals/${a.id}`}>
                          <span className="activity-icon">
                            <Scale size={18} />
                          </span>
                          <span>
                            <strong>Апелляция #{a.id}</strong>
                            <small>
                              Оценка #{a.evaluation_id} · {dateLabel(a.created_at)}
                            </small>
                          </span>
                          <StatusBadge status={a.status} />
                        </Link>
                      ))}
                  </div>
                ) : (
                  <EmptyState title="Активных апелляций нет">
                    История решений появится здесь.
                  </EmptyState>
                )}
              </Card>
            </div>
          </>
        )}
      </QueryState>
    </>
  )
}
