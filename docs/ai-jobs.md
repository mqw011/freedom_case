# Durable AI jobs и Stage 3 API

## Жизненный цикл

`queued → running → completed | failed | cancelled`. Временный сетевой сбой с оставшимся бюджетом возвращает job в queued с next_attempt_at. Ручной retry допускается только для failed и добавляет новый бюджет попыток, сохраняя старые AIJobAttempt. Новая явная оценка без прежнего idempotency_key создаёт отдельный job/Evaluation.

Таблицы `ai_jobs`, `ai_batches`, `ai_job_attempts`, `ai_worker_lease` создаются новой Alembic-миграцией. Исходные миграции и оценки не изменены.

## Надёжность

- Версия чек-листа закрепляется в момент создания job/batch. Активация другой версии не влияет на выполняющиеся задачи.
- Повтор одного idempotency_key с тем же телом возвращает прежний job/batch, даже если активная версия уже другая. Иное тело с тем же ключом — 409. Unique constraints защищают от дублей при гонках.
- Singleton worker lease запрещает второй активный worker на этой БД. Внутри процесса параллелизм ограничен `LLM_MAX_CONCURRENCY`, по умолчанию 1.
- Claim — атомарный conditional UPDATE с уникальным claim_token. Heartbeat обновляет lease worker и его jobs, по умолчанию lease 90 сек и polling 1 сек.
- После падения старые running jobs восстанавливаются после истечения lease. Попытка отмечается interrupted; задача снова queued либо failed при исчерпании бюджета. Устаревший owner/token не может записать результат.
- SQLAlchemy session закрывается **до** HTTP inference. Сохранение Evaluation и completed-job выполняется одной короткой транзакцией. Ошибка откатывает оба изменения.
- Cancel queued завершается сразу. Cancel running ставит cancel_requested; worker прерывает ожидающий HTTP запрос. Провайдер может ещё некоторое время считать на своей стороне, но результат отменённой задачи не записывается. Уже completed отменять нельзя (409).
- SIGINT/SIGTERM прекращает приём задач, отменяет текущие запросы и возвращает незавершённые задачи по retry policy. Жёсткий crash покрывается lease recovery.

Без Redis/Celery. SQLite подходит для одного локального worker. Для иной СУБД необходимо отдельно проверить конкуренцию и миграции; бизнес-логика не опирается на SQLite-only SQL.

## Запуск

Из backend после миграций:

```bash
uv run python -m app.ai.worker
uv run python -m app.ai.worker --once
uv run python -m app.ai.worker --max-jobs 3
```

Последние две команды — альтернативные ограниченные запуски, не параллельные workers. `--once` заканчивает после одной попытки или пустой очереди. `--max-jobs` считает попытки claim, включая retries. `AI_AUTO_START_WORKER=false` по умолчанию. Если включить auto-start, lifespan приложения управляет worker; для разработки предпочтителен отдельный процесс и отсутствие auto-worker при reload.

`AI_JOB_ENABLED=false` запрещает новые задания/ручной retry и запуск worker. Просмотр истории и Stage 1 продолжают работать.

## REST

Все пути начинаются `/api`. Job submission возвращает 202, чтение/отмена — 200.

- `POST /ai/evaluations` → AIJobRead. Тело AIJobCreate: conversation_id; необязательные checklist_version_id, checklist_id, idempotency_key.
- `POST /ai/batches` → AIBatchRead. AIBatchCreate: conversation_ids **или** dataset_id/language/channel; также version/checklist/key. До 10000 выбранных разговоров. Каждый — отдельный job, snapshot выбора не меняется при новых импортах.
- `GET /ai/jobs?status=queued&batch_id=1&conversation_id=1&offset=0&limit=50` → Page[AIJobRead]. Фильтры необязательны.
- `GET /ai/jobs/{id}` → AIJobRead.
- `GET /ai/jobs/{id}/attempts?offset=0&limit=50` → Page[AIJobAttemptRead].
- `POST /ai/jobs/{id}/retry` → AIJobRead, только failed.
- `POST /ai/jobs/{id}/cancel` → AIJobRead.
- `GET /ai/batches?offset=0&limit=50` → Page[AIBatchRead].
- `GET /ai/batches/{id}` → AIBatchRead.
- `GET /ai/batches/{id}/jobs?offset=0&limit=50` → Page[AIJobRead].
- `POST /ai/batches/{id}/retry-failed` → {batch_id,retried}.
- `GET /ai/health` → AIHealth: enabled, provider, worker. Backend/БД health остаётся `/health`.

Пример постановки без передачи оценок:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/api/ai/evaluations \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":1,"idempotency_key":"demo-1"}'
```

**AIJobRead:** id, status, conversation_id, checklist_version_id, provider, model, attempts/max_attempts, даты, next_attempt_at, cancel_requested, batch_id, evaluation_id, error_code, safe_error_message, diagnostics. Raw prompt/response отсутствуют.

**AIBatchRead:** id, checklist_version_id, created_at, total, queued, running, completed, failed, cancelled, percentage. Процент — `(completed+failed+cancelled)/total*100`, поэтому 100% не означает 100% успешных оценок. Decimal возвращается строкой. Список job IDs берётся из отдельного paginated endpoint.

**AIHealth:** provider.available означает доступность API и наличие заданной модели, не гарантию успешного следующего inference. worker.available вычисляется по живому lease. Отсутствующий Ollama не блокирует ручные API.

## Интеграция Stage 3

`frontend/src/api/ai.js` уже предоставляет Fetch helpers с AbortSignal. UI должен опрашивать jobs/batches и переходить по evaluation_id только после completed. Ошибки безопасны для показа пользователю. needs_human_review и voice_transcript_only показывать явно. Failed нельзя отображать как оценку 0.

- Dashboard: `/datasets`, `/conversations`, `/evaluations`, `/ai/batches`, `/ai/jobs` (везде учитывать pagination; агрегированного dashboard endpoint пока нет).
- Conversations: существующие list/detail/messages и `/conversations/{id}/evaluations`.
- AI status: AIJobRead/AIBatchRead, отдельные attempts, health.
- Results: `/evaluations/{id}` (EvaluationDetail; список — Page[EvaluationRead]), source, initial/final, current_* и critical_violation.
- Evidence navigation: evidence.message_id/end_message_id → реальные сообщения ConversationDetail; message_index определяет порядок.
- Checklist Editor: существующие checklist/version/activate DTO; новые jobs используют новую активную версию.
- Appeals: существующие create/list/detail/decision операции; AI-оценки сохраняют те же immutable snapshots и совместимы с пересмотром.

Авторизации пока нет по условию хакатона. Публичный deployment Stage 4 обязан защитить API и worker-инфраструктуру до внешнего доступа.
