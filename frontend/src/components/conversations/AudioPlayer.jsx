import { useState } from 'react'
import { ExternalLink, Headphones } from 'lucide-react'
export default function AudioPlayer({ url }) {
  const [failed, setFailed] = useState(false)
  const safe = typeof url === 'string' && /^https?:\/\//i.test(url)
  return (
    <section className="audio-panel">
      <h3>
        <Headphones size={17} /> Запись звонка
      </h3>
      <p className="muted">
        Оценка основана на транскрипте. Интонация и дикция не анализировались.
      </p>
      {safe ? (
        <>
          <audio
            controls
            preload="none"
            src={url}
            onError={() => setFailed(true)}
            aria-label="Запись разговора"
          />
          {failed && (
            <p role="alert">
              Не удалось воспроизвести запись. Источник может ограничивать доступ или срок ссылки.
            </p>
          )}
          <a href={url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
            Открыть оригинальную запись <ExternalLink size={14} />
          </a>
        </>
      ) : (
        <p>Ссылка на аудиозапись недоступна.</p>
      )}
    </section>
  )
}
