# REST API Stage 1

Префикс `/api`. Интерактивный контракт: `/docs`, JSON Schema: `/openapi.json`. Все request/response модели Pydantic находятся в `backend/app/schemas/`. Числовые внутренние IDs отличаются от текстового `conversation_id` организаторов.

Запросы JSON используют `Content-Type: application/json`; import-json — multipart/form-data. Дополнительные неизвестные поля запрещены. Ответы Decimal сериализованы строками, даты — ISO UTC. Пагинация списков: `offset=0`, `limit=50`, максимум 100; сортировка по внутреннему `id ASC`. Ответ списка: `{"items": [...], "total": 3, "offset": 0, "limit": 50}`. Исключения: список сообщений и список версий возвращаются массивами в стабильном порядке.

## Health

`GET /api/health` → `200 {"status":"ok","database":"ok"}` после проверки соединения, alembic_version и таблицы checklists. Недоступная/неподготовленная БД → `503`.

## Datasets

- `POST /api/datasets/import` → 201, тело `{"group_id":"DEV"}`. Формат group_id: 1–64 ASCII буквы/цифры/`_`/`-`, первый символ — буква или цифра. URL задаётся только конфигурацией сервера.
- `POST /api/datasets/import-json` → 201, multipart `file` с полным envelope организаторов. Полный пример: `examples/synthetic-dataset.json`.
- `GET /api/datasets` → страница наборов.
- `GET /api/datasets/{id}` → метаданные набора или 404.

Пример отчёта:

```json
{
  "dataset": {
    "id": 1, "group_id": "LOCAL-EXAMPLE", "source": "json_file",
    "imported_at": "2026-11-07T08:00:00Z", "total_records": 1, "import_status": "complete"
  },
  "declared_records": 1, "received_records": 1, "inserted": 1, "skipped": 0, "warnings": []
}
```

Повторная идентичная загрузка также возвращает 201 с inserted=0/skipped=N; новая операция импорта завершена успешно, существующие записи не меняются. Несовпавшее содержимое известного диалога — 409. Все записи пакета сохраняются атомарно. Пустой корректный массив допустим. Объявленное число не заменяет фактическое.

Envelope требует `error`, строго boolean `isSuccess`, `data.dataset_group_id`, неотрицательный integer `total_records`, `records`. Поддерживаются RU/KZ/EN, agent chat/voice call и client/operator/bot/system. Transcript непустой; каждый timestamp валидируется, но сохраняется дословно. Для chat audio_url=null. Для call HTTP(S) audio_url либо null; при отсутствии записи транскрипт всё равно может быть импортирован.

## Conversations

- `GET /api/conversations`: `offset`, `limit`, `search` по подстроке внешнего conversation_id, `language`, `channel`, `dataset_id`. `%` и `_` в поиске трактуются как текст, а не wildcard SQL.
- `GET /api/conversations/{id}`: metadata + messages + audio_url.
- `GET /api/conversations/{id}/messages`: массив с `id`, `conversation_id` (внутренний FK), `message_index` от 0, `speaker`, `timestamp_raw`, `text`.
- `GET /api/conversations/{id}/evaluations`: страница исторических оценок.

```bash
curl --fail-with-body 'http://127.0.0.1:8000/api/conversations?language=KZ&channel=agent%20chat&limit=10'
curl --fail-with-body http://127.0.0.1:8000/api/conversations/1/messages
```

## Checklists

- `GET /api/checklists`: страница чек-листов и active_version_id.
- `POST /api/checklists`: `{name, description, version: {criteria: [...]}}`; создаёт и активирует первую версию, 201.
- `GET /api/checklists/{id}`: метаданные и active_version_id.
- `GET /api/checklists/{id}/versions`: массив полных версий по version_number ASC, включая criteria.
- `POST /api/checklists/{id}/versions`: `{criteria: [...]}`, новая полная версия, 201.
- `POST /api/checklists/{id}/activate`: `{"version_id":2}`, 200. Версия обязана принадлежать чек-листу и иметь сумму весов 100.

Пример самостоятельного пользовательского чек-листа:

```json
{
  "name": "Custom quality",
  "description": "Пользовательская шкала",
  "version": {
    "criteria": [{
      "code": "resolution", "title": "Решение запроса", "description": "Полнота ответа",
      "section": "Консультация", "criterion_type": "scale", "weight": "100",
      "allowed_values": ["0", "2", "4"], "max_score": "4",
      "allow_na": true, "na_condition": "Клиент не сформулировал запрос",
      "scale_labels": {"0":"Нет ответа", "2":"Частичный ответ", "4":"Полный ответ"},
      "display_order": 1
    }]
  }
}
```

Вход criterion: code/title/description/section/type/weight/allowed_values/max_score/allow_na/na_condition/scale_labels/display_order. `criterion_type`: binary, scale или flag. API требует имя `criterion_type`, а не сокращённое `type` из концептуального примера задания. Numeric max/ступени/веса — Decimal, допускаются JSON числа или десятичные строки. Binary/flag требуют [0,1]. Старые версии не редактируются; PATCH/DELETE не предоставлены намеренно. На новую версию отправляйте входные поля, без `id` и `checklist_version_id` из read-response.

## Evaluations

- `POST /api/evaluations` → 201, подробная оценка. Принимает conversation_id, checklist_version_id, source (manual по умолчанию, также test), полный results.
- `GET /api/evaluations`: страница, фильтры conversation_id/source и пагинация.
- `GET /api/evaluations/{id}`: итоги, исходные и текущие результаты, evidence, appeal_ids.

Ответы binary/flag: `"yes"`, `"no"`; N/A: `"na"`. Scale: разрешённое число/десятичная строка. `true` не заменяет yes. Результат каждого критерия обязателен, включая безбалльный flag. Автоматического определения N/A по транскрипту нет: клиент передаёт ответ и объяснение.

Полный запрос с эталоном 81.88: `examples/manual-evaluation.json`. Одно значение results:

```json
{
  "criterion_code": "01",
  "answer": "yes",
  "explanation": "Оператор поздоровался и представился в первом ответе",
  "evidence": [{
    "evidence_type": "quote", "message_id": 2,
    "excerpt": "Здравствуйте! Я Анна.", "explanation": "Приветствие и представление"
  }]
}
```

Evidence:

- `quote`: message_id и точный непустой excerpt обязательны, end_message_id запрещён.
- `range`: message_id и end_message_id обязательны, диапазон включителен; порядок проверяется через message_index. Если excerpt задан, он относится к начальной реплике.
- `absence`: объяснение отсутствующего действия; без IDs областью является весь диалог, с message_id — одна реплика, с обоими IDs — диапазон. Это утверждение оценщика, не автоматически доказанная семантика.

Любой ID должен принадлежать оцениваемому диалогу; неверная цитата/диапазон/чужая реплика → 422. Evidence можно не передавать для ручного результата; объяснение обязательно.

Evaluation содержит `initial_score`, `final_score`, `initial_critical_violation`, `critical_violation`, `revision`, `source`, `status=completed`, UTC даты. CriterionResult содержит исходные `answer`, `raw_score`, `weighted_score`, `is_na`, explanation/evidence и вычисляемые `current_answer`, `current_raw_score`, `current_weighted_score`, `current_is_na`. Значение weighted_score — исходный весовой вклад до нормализации N/A; итог нормализован отдельно.

## Appeals

- `POST /api/evaluations/{id}/appeals` → 201, тело `{criterion_result_id, comment}`.
- `GET /api/appeals`: страница, необязательный status=pending/upheld/revised.
- `GET /api/appeals/{id}`: апелляция и вложенное решение либо decision=null.
- `POST /api/appeals/{id}/decision`: решение проверяющего, 200.

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/api/evaluations/1/appeals \
  -H 'Content-Type: application/json' \
  -d '{"criterion_result_id":7,"comment":"Прошу пересмотреть завершение"}'

curl --fail-with-body -X POST http://127.0.0.1:8000/api/appeals/1/decision \
  -H 'Content-Type: application/json' \
  -d '{"decision":"revised","revised_answer":"yes","reason":"Проверено завершение диалога"}'
```

Идентификаторы примера справедливы для первого импорта/оценки в чистой БД; используйте фактические IDs из ответов.

Подтверждение: `{"decision":"upheld","reason":"Оценка подтверждена"}` без revised_answer. Изменение: decision=revised, новое допустимое revised_answer и непустая reason. Если ответ не изменился, используйте upheld. Открытая дублирующая апелляция и повторное решение закрытой → 409. После закрытия можно подать новую апелляцию, сохранив предыдущие решения.

Решение возвращает до/после ответа, баллов критерия и итоговой оценки. Повторное чтение Evaluation показывает новый final_score и current_*; initial_score, исходные CriterionResult и evidence остаются прежними. При изменении флага пересчитывается critical_violation без самостоятельного штрафа.

## Ошибки

```json
{"error":{"code":"invalid_results","message":"Criterion 01 does not allow N/A"}}
```

Ошибки Pydantic дополнительно возвращают details с loc/type/message, без входных значений и внутренних исключений.

- 400: синтаксически некорректный JSON-файл импорта.
- 404: отсутствующая сущность.
- 409: изменённый существующий диалог, конфликт уникальности/конкурентности, закрытая апелляция, неизменяемый snapshot.
- 422: невалидный запрос/результат/конфигурация/evidence/файл/размер локального файла. Синтаксическая ошибка JSON обычного request body также обрабатывается FastAPI как 422.
- 502: внешний API вернул ошибку, redirect, таймаут, неправильную структуру/группу или слишком большой ответ.
- 503: DATASET_API_URL не задан либо БД недоступна/занята/не мигрирована.
- 500: непредвиденная внутренняя ошибка с безопасным общим сообщением.

Авторизации нет по условиям Stage 1. Для будущего frontend заявитель и проверяющий различаются вызываемыми действиями, не вымышленными серверными ролями.

## AI Stage 2

AI job/batch API, статусы, polling, retry/cancel, health и frontend DTO описаны в [ai-jobs.md](ai-jobs.md). Endpoint `/evaluations` остаётся ручным/test; `source=ai` туда передавать нельзя. Автоматический анализ запускается `POST /api/ai/evaluations` с conversation_id, без готовых результатов.


## Использование из Stage 3

Новых production endpoints в Stage 3 нет. `frontend/src/api/` содержит централизованные клиенты всех существующих действий. Точный источник контракта — `/openapi.json`; UI сохраняет Decimal строками в запросах. Health backend/provider/worker отображается раздельно.

- Dashboard/глобальные фильтры: пройти все Page до total для conversations, datasets, evaluations, appeals, ai/jobs, ai/batches, checklists. Последняя completed evaluation на conversation → final_score; null исключить, failed/cancelled job не преобразовывать в 0.
- Conversation detail: `/conversations/{id}` + список evaluations → `/evaluations/{id}` + **закреплённая** версия из `/checklists/{id}/versions`.
- Evidence: настоящий message_id/end_message_id и точная цитата; отсутствие границ absence означает весь разговор.
- Editor: POST checklist или POST полная новая version; activation отдельным POST. Сумма не 100 допустима для сохранения новой неактивной версии, запрещена при активации.
- Appeal: criterion_result_id из EvaluationDetail, не code; решение возвращает AppealRead, затем обновляются evaluation и dashboard.
- AI creation/retry возвращают **202**, не 201. Job response содержит `id`, не `job_id`. Attempt history — **Page**, versions — обычный массив. Batch percentage считает все terminal states.
- Import JSON — multipart поле `file`, не JSON body. Group import принимает только group_id, URL остаётся backend-конфигурацией.

Ключи polling/caching и безопасная обработка ошибок: [frontend architecture](frontend-architecture.md). Примеры браузерных действий и пять минут защиты: [UI workflows](ui-workflows.md).
