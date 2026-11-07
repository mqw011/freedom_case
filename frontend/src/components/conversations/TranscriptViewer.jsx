import { Copy } from 'lucide-react'
import { Badge, Button } from '../ui'
import { useToast } from '../ui/Toast'
const roles = {
  client: 'Клиент',
  operator: 'Оператор',
  bot: 'Бот',
  system: 'Система',
}
export default function TranscriptViewer({ messages, selection }) {
  const notify = useToast()
  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text)
      notify('Реплика скопирована')
    } catch {
      notify('Копирование недоступно в этом браузере')
    }
  }
  return (
    <div className="transcript" aria-label="Транскрипт">
      {messages.map((m) => {
        const highlighted = selection?.ids.includes(m.id),
          excerpt = highlighted && m.id === selection.first && selection.excerpt
        const start = excerpt ? m.text.indexOf(excerpt) : -1
        return (
          <article
            key={m.id}
            id={`message-${m.id}`}
            data-message-id={m.id}
            tabIndex={-1}
            className={`message ${m.speaker} ${highlighted ? 'highlighted' : ''}`}
          >
            <div className="message-meta">
              <Badge tone={m.speaker}>{roles[m.speaker]}</Badge>
              <time>{m.timestamp_raw}</time>
              <span>#{m.message_index}</span>
              <Button
                variant="ghost"
                aria-label={`Копировать реплику ${m.message_index}`}
                onClick={() => copy(m.text)}
              >
                <Copy size={14} />
              </Button>
            </div>
            <p>
              {start >= 0 ? (
                <>
                  {m.text.slice(0, start)}
                  <mark>{excerpt}</mark>
                  {m.text.slice(start + excerpt.length)}
                </>
              ) : (
                m.text
              )}
            </p>
          </article>
        )
      })}
    </div>
  )
}
