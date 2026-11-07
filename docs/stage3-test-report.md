# Stage 3 test report — 2026-11-07

## Итог

**Stage 3 COMPLETE.** Проверен полноценный UI поверх настоящих API. Stage 2 остаётся **PARTIAL**; GPU inference в этой проверке не запускался. RunPod deployment не выполнялся.

## Воспроизводимая регрессия

- `uv sync --locked --python 3.12`: успешно, Python 3.12.13.
- `uv run pytest`: **249 passed, 0 failed**, включая все прежние 248 и новый тест изоляции/содержимого UI sandbox.
- `uv run ruff check .`: успешно.
- `uv run alembic check`: **No new upgrade operations detected**. Production-схема не изменялась; миграции чистой базы также выполнялись при каждом e2e запуске.
- `npm ci`: успешно, lockfile воспроизводится; npm audit при установке — 0 vulnerabilities.
- `npm run lint`: успешно.
- `npm run build`: успешно; JS bundle ~418 kB / ~131 kB gzip, CSS ~20 kB / ~5 kB gzip.
- `npm run test`: **65 passed, 0 failed**, 3 файла Vitest/Testing Library.
- `npm run format:check`: успешно.
- `npm run test:e2e`: **16 passed, 0 failed**, Chromium, 1 worker, ~41 сек.

Тесты сообщают предупреждение Starlette о будущей замене httpx test transport; npm сообщает, что сохранённая из исходного проекта версия ESLint 9 больше не поддерживается. Эти предупреждения не являются падениями; обновление совместимых major-версий не входило в Stage 3. Установленные зависимости не показали известных уязвимостей при npm ci.

## Что проверено в браузере

Все изменяющие сценарии выполнялись через реальные FastAPI endpoints на новой временной SQLite; JSON backend не подменялся клиентским state. Исключения: отдельный тест network/empty/loading намеренно перехватывает только адрес тестового API. API организаторов заменён локальным HTTP mock, не production DEV.

1. Dashboard: полный набор из 65 синтетических диалогов, 2 test evaluations, average 90.94, переход к списку.
2. Глобальные RU/KZ/EN, chat/voice, поиск, pagination до 65-й записи, сохранение фильтров при Back; исправлена гонка быстрых изменений фильтров.
3. Quote/range/absence по настоящим IDs, точная подсветка, focus/scroll в разговоре из 115 сообщений.
4. Новая версия чек-листа, изменение весов и формулировки, активация, неизменность исходной версии/evaluation, version pinning нового job.
5. Создание апелляции и оба решения: revised и upheld. Initial **81.88** сохраняется; final после revised=yes для завершения — **88.13**. Dashboard обновляет average до 94.07.
6. Отмена queued, повтор synthetic failed job, сохранение истории attempts, отсутствие evaluation у ошибки.
7. Настоящий batch API создаёт **65 queued**, completed=0, progress=0, source=ai evaluations=0. Никакого inference и фиктивных successful jobs.
8. Импорт по group_id: inserted=2; повтор: skipped=2; JSON импорт добавляет 1; ошибка HTTP внешнего mock отображается безопасно. Итоговый тестовый набор увеличивается до 68.
9. Звонок: ISO timestamps, audio preload none, обработка ошибки и безопасный external fallback; все разделы доступны при provider/worker offline.
10. Keyboard, skip-link без нарушения HashRouter, native modal focus/Escape/restore, mobile menu.
11. Backend offline, безопасная ошибка, empty и loading.
12. Все основные маршруты при **1440, 1280, 768, 390 px**; нет горизонтального overflow страницы, console errors или unhandled page errors. Просмотрены синтетические снимки desktop/tablet/mobile; evidence прокручивается в видимую область и на mobile.
13. Новый чек-лист с пользовательской шкалой 0/3/9, описанием ступени, N/A, добавлением/удалением критерия и сохранением через API.
14. Batch retry-failed возвращает только failed, сохраняя cancelled.
15. Некорректные ID и отсутствующие записи дают ошибки, а не бесконечную загрузку.
16. Axe WCAG A/AA automated checks на основных страницах, в редакторе и dialog: **0 обнаруженных нарушений**. Дополнительно проверена клавиатура; это не заявление о полной сертификации accessibility.

Vitest отдельно проверяет Decimal/нулевой балл/null/N/A, статусы, данные за первой сотней, согласованность шкал/весов, API timeout/cancel/errors, защиту от HTML-инъекции, evidence mapping, таблицы, формы, progress и health.

## Рабочая база: read-only проверка

Содержимое **всех 16 таблиц**, включая timestamps и очередь, сравнивалось до/после по количеству строк и SHA-256 сериализованных строк в стабильном порядке. Все хэши совпали. Локальный контрольный файл находится в игнорируемом `backend/data/` и не публикуется.

- DEV: **65** conversations, **1268** messages.
- RU **35**, KZ **15**, EN **15**; **60** chats / **5** calls.
- Existing evaluations: **1**, source AI, восемь результатов и восемь evidence — сохранены.
- AI jobs: **9**, attempts **6**, batches **0** — сохранены без изменений.
- Checklist **1**, version **1**, criteria **8** — сохранены.
- Appeals **0**, decisions **0** — рабочая база не использовалась для тестовых апелляций.

Рабочие `/api/health`, `/docs`, `/openapi.json`, datasets, conversations, checklists, appeals, AI jobs/batches/health ответили HTTP 200. Provider и worker сообщили unavailable. Браузером открыты настоящий Dashboard, список и existing evaluation: **0 JavaScript errors, 0 mutating requests, 0 screenshots**. Тексты реальных диалогов не включены в артефакты.

## Ограничения и следующий этап

Автоматический браузерный прогон выполнен на Chromium, не на Safari/Firefox. Воспроизведение реальных внешних аудиоссылок зависит от доступности источника; безопасный fallback реализован и проверен на синтетическом URL. Полные метаданные загружаются клиентом по всем страницам: для существенно больших наборов понадобится серверная агрегация. Автоматические accessibility-проверки дополнены базовой клавиатурной проверкой, но не пользовательским исследованием со screen reader.

GPU Xid 79 и незавершённые real inference проверки Stage 2 остаются отдельной задачей RunPod. Драйверы, Ollama, модель, Scoring Engine, production API и migration history в Stage 3 не менялись. [RunPod handoff](runpod-readiness.md).
