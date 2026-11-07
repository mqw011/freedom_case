# Freedom Broker — Conversation Quality Analytics

CQA хранит клиентские диалоги, версии чек-листов, оценки с доказательствами и историю апелляций. **Stage 1 реализует хранение и бизнес-логику; Stage 2 добавляет локальную AI-оценку через Ollama, проверку доказательств и постоянную очередь заданий.**

Ручной API принимает структурированные ответы по критериям. AI API ставит задания в очередь; отдельный worker получает ответы модели и использует тот же сервис сохранения. Backend валидирует ответы, проверяет ссылки на реплики, рассчитывает баллы и сохраняет результат. Никаких случайных оценок, скрытых LLM-вызовов и загрузок моделей при запуске нет.

## Состав

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, SQLite, HTTPX, Uvicorn.
- React, Vite, JavaScript, Fetch API, HashRouter. Минимальная страница и статус backend; рабочие интерфейсы разделов относятся к Stage 3.
- Pytest, Ruff, ESLint; зависимости закреплены в `backend/uv.lock` и `frontend/package-lock.json`.
- Схема Stage 1 дополнена ai_jobs, ai_batches, ai_job_attempts и ai_worker_lease; миграции сохраняют существующие диалоги и оценки.

```text
backend/app/api → Pydantic DTO → сервисы → SQLAlchemy → SQLite
                                     ↓
                          EvidenceValidator → Scoring Engine
frontend → Fetch API → /api
AI worker → AIEvaluator → StructuredEvaluation → тот же сервис оценки
```

**Проверка Stage 2 пока PARTIAL:** аппаратный отказ GPU и timeout CPU не позволили завершить обязательные real inference проверки. Подробности — в [отчёте Stage 2](README_STAGE2.md).

Подробности: [архитектура](docs/architecture.md), [API](docs/api.md), [расчёт](docs/scoring.md), [roadmap](docs/roadmap.md), [отчёт Stage 1](README_STAGE1.md), [запуск Stage 2](README_STAGE2.md), [AI engine](docs/ai-engine.md), [AI jobs](docs/ai-jobs.md).

## Требования для CachyOS

Нужны Git, `uv`, Node.js ≥22.12 и npm. Python 3.12 закреплён в `backend/.python-version`; `uv` может установить его автоматически. Системный Python CachyOS менять не нужно. Для системной установки доступны пакеты CachyOS/Arch `git`, `uv`, `nodejs`, `npm`.

Проверенное окружение: Python 3.12.13 внутри venv, Node.js 26.13.0, npm 12.2.1. SQLite входит в используемую сборку Python. GPU, Ollama, Docker и отдельный сервер БД для Stage 1 не нужны.

## Установка backend

Из корня существующего репозитория:

```bash
cd backend
uv sync --locked --python 3.12
test -f .env || cp .env.example .env
uv run alembic upgrade head
uv run python -m app.seed.default_checklist
```

`alembic upgrade head` создаёт схему **и автоматически добавляет точный исходный чек-лист из 8 критериев**. Последняя команда — идемпотентная проверка/восстановление начального чек-листа; она не меняет активную версию уже существующего чек-листа. Не использовать `create_all()` и не создавать таблицы вручную.

Файл `.env` читается из текущего каталога. Все backend-команды ниже выполняются из `backend/`; корневой `.env.example` — справочная копия, рабочий файл — `backend/.env`. Уже существующий `.env` не перезаписывайте.

Основные параметры:

```dotenv
APP_ENV=development
DATABASE_URL=sqlite:///./data/cqa.db
CORS_ORIGINS=http://localhost:5173
DATASET_API_URL=
DATASET_API_TIMEOUT=30
IMPORT_MAX_BYTES=20971520
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:4b
LLM_API_KEY=
LOG_LEVEL=INFO
```

- `DATABASE_URL`: относительный SQLite-путь считается от текущего каталога. Для другого рабочего каталога задайте абсолютный URL `sqlite:////absolute/path/cqa.db`.
- `CORS_ORIGINS`: список разрешённых origin через запятую. `http://localhost:5173` и `http://127.0.0.1:5173` — разные origin.
- `DATASET_API_URL`: доверенный адрес организаторов; пуст по умолчанию. Поддерживает `{group_id}` в пути/строке запроса. Без шаблона query-параметр `group_id` добавляется или заменяется с сохранением остальных параметров, включая подпись.
- `DATASET_API_TIMEOUT`: HTTP timeout в секундах; `IMPORT_MAX_BYTES` ограничивает размер файла и ответа внешнего API.
- `LLM_*`, `AI_*`: параметры inference и очереди, полный список в `.env.example` и [AI engine](docs/ai-engine.md). По умолчанию используется локальный Ollama; backend не скачивает модель и не запускает worker автоматически.

Секреты, `.env`, базы, `.venv`, `node_modules` и сборки исключены из Git.

## Запуск

Первый терминал, из `backend/`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Второй терминал, из корня репозитория:

```bash
cd frontend
npm install
test -f .env || cp .env.example .env
npm run dev
```

Для воспроизводимой установки frontend из lockfile также поддерживается `npm ci`. Backend URL задаётся в `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api
```

Адреса:

- Приложение: http://localhost:5173
- Health: http://127.0.0.1:8000/api/health
- Swagger: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

Health проверяет соединение с БД и наличие мигрированной схемы. Без миграций возвращает `503`, а не декоративный успех. Backend пишет JSON-логи без тел диалогов, токенов и URL внешнего API. `--no-access-log` отключает отдельный стандартный access log Uvicorn.

HashRouter и относительный `base` Vite позволяют в дальнейшем адаптировать frontend для HTML-компонента Dynamics 365; сама интеграция Dynamics пока не реализована.

## Импорт DEV-набора

Настоящий DEV API проверен 7 ноября 2026 года: 65 диалогов импортированы в локальную БД, повторный импорт пропускает все 65 записей. Подробный аудит — в [отчёте Stage 1](README_STAGE1.md#проверка-настоящего-dev-api--2026-11-07). Подписанный URL хранится только в локальном `backend/.env` и отсутствует в Git. Для новой установки укажите полученный от организаторов адрес в `DATASET_API_URL`, перезапустите backend и выполните:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/api/datasets/import \
  -H 'Content-Type: application/json' -d '{"group_id":"DEV"}'
```

Если URL не настроен, ответ будет `503 dataset_not_configured`. Публичный API принимает только `group_id`, а не произвольный URL. Redirect внешнего сервера не выполняется, аудио не скачивается. Реальные 65 DEV-диалогов не входят в репозиторий и не подменяются примерами.

Для локальной проверки из `backend/`:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/api/datasets/import-json \
  -F 'file=@../examples/synthetic-dataset.json;type=application/json'
curl --fail-with-body 'http://127.0.0.1:8000/api/conversations?language=RU&limit=10&offset=0'
```

`examples/synthetic-dataset.json` содержит **один явно синтетический** диалог группы `LOCAL-EXAMPLE`. Тесты используют отдельные временные базы и локальный mock HTTP API. Никакой автоматической загрузки фиктивных диалогов в рабочую БД нет.

Повторный импорт идентичного диалога возвращает `skipped`; новый диалог той же группы добавляется. Если содержимое существующего диалога изменилось, весь импорт откатывается с `409`. Идентичность — пара `(group_id, conversation_id)`: пересекающиеся идентификаторы разных наборов разрешены. Несоответствие `total_records` фактическому массиву отражается в `warnings`; импортируется весь фактический массив. Пустой корректный набор допускается.

## Ручная проверка оценки

После локального импорта в чистую БД (conversation_id=1, checklist_version_id=1):

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/api/evaluations \
  -H 'Content-Type: application/json' --data-binary @../examples/manual-evaluation.json
```

Ожидаемые `initial_score` и `final_score`: **`"81.88"`**. В непустой БД замените идентификаторы в запросе на возвращённые API. Ответы в этом файле предназначены для проверки арифметики; это не заключение AI о синтетическом диалоге.

Decimal-поля в JSON возвращаются строками, чтобы клиент не терял точность. Формула: `SUM(raw/max*weight) / SUM(applicable_weight) * 100`; итог округляется `ROUND_HALF_UP` до двух знаков. Грубая ошибка отмечается отдельным флагом и не обнуляет оценку.

Полный повторяемый сценарий через работающий сервер:

```bash
uv run python ../scripts/smoke_api.py --base-url http://127.0.0.1:8000/api
```

Скрипт создаёт отдельную группу `LOCAL-SMOKE-*` и собственный чек-лист, проверяет идемпотентность импорта, сообщения, оценку `81.88`, новую версию/активацию, неизменность старой оценки, апелляцию и пересчёт до `88.13`. Исходный активный чек-лист пользователя не переключает. Запускайте на локальной тестовой БД: данные сценария намеренно остаются доступными для просмотра.

## Проверки

Backend, из `backend/`:

```bash
uv run pytest
uv run ruff check .
uv run alembic check
```

Frontend, из `frontend/`:

```bash
npm run lint
npm run build
npm audit
```

Из корня репозитория можно дополнительно проверить вспомогательные скрипты:

```bash
uv run --project backend ruff check .
git diff --check
```

Тесты проверяют реальные HTTP-ответы и изменения в временной SQLite: арифметику, импорт, API, апелляции, evidence, версии, миграции upgrade/downgrade/upgrade и конкурентные изменения. Внешний API организаторов в тестах не вызывается.

## Ограничения Stage 1

- Настоящий DEV API проверен, но подписанная ссылка и импортированные диалоги доступны только в локальном окружении и не поставляются с Git-репозиторием. Новая установка требует собственного разрешённого доступа к API.
- Авторизации нет по условиям хакатона. Базовый запуск слушает localhost.
- STT и полноценный интерфейс оценки ещё не реализованы. Аудио хранится ссылкой; AI оценивает существующий транскрипт.
- Структурные evidence-проверки дополнены семантическим AI-аудитом. Это не заменяет экспертный контроль, особенно для KZ и непроверенных финансовых утверждений.
- SQLite подходит для локального MVP; при конкурентной записи клиент может получить `409`/`503` и должен обновить данные перед повтором. PostgreSQL в Stage 1 не установлен и не тестировался.
- Saved versions неизменяемы; изменения создаются новой полной версией. Версия с несогласованной суммой весов может храниться, но не активироваться и не использоваться для оценки.

## Следующие этапы

Stage 2 реализует Ollama/Qwen и OpenAI-compatible transport, JSON Schema, семантическую проверку evidence, retries, длинные диалоги и пакетные задания. Вход — `EvaluationContext`, выход — `StructuredEvaluation`; внутренний `EvaluationSubmission(source="ai")` проходит через уже существующий `EvaluationService` без изменения Scoring Engine.

Stage 3: Dashboard, Conversations, детали/evidence/аудио, редактор чек-листа, Appeals. Stage 4: расширенные интеграционные проверки, Docker, RunPod, HTTPS и эксплуатационная документация.
