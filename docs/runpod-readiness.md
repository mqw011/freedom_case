# Stage 4 handoff — RunPod integration testing

Stage 3 не создаёт облачные ресурсы и не настраивает публичный сервер. Готовы React static build, FastAPI API, durable SQLite jobs, отдельный worker, импорт, версии чек-листа, evidence, апелляции и polling. Stage 2 остаётся PARTIAL.

## Frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=/api npm run build
```

Результат — `frontend/dist`, относительные ассеты, HashRouter. `VITE_API_BASE_URL` — build-time переменная с префиксом `/api`; при смене origin пересобрать. Не включать секреты в `VITE_*`. `VITE_DEMO_MODE` для production не задавать/false. Статические файлы отдавать через reverse proxy, Vite dev server публично не открывать. Для Dynamics 365 остаётся проверить iframe/origin/CSP принимающей системы.

## Backend и worker

Из `backend/`, после настройки окружения:

```bash
uv sync --locked --python 3.12
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Отдельный процесс, только когда inference provider исправен:

```bash
uv run python -m app.ai.worker
```

Проверить команду worker и варианты CLI можно через `README_STAGE2.md` / `docs/ai-jobs.md`. Не включать одновременно самостоятельный worker и `AI_AUTO_START_WORKER=true`.

Минимальная конфигурация: `DATABASE_URL` с абсолютным путём на persistent volume, `CORS_ORIGINS` реального HTTPS frontend origin, секретный `DATASET_API_URL`, `DATASET_API_TIMEOUT`, `IMPORT_MAX_BYTES`; `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_CONTEXT_LENGTH`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT`, `LLM_MAX_RETRIES`, `LLM_MAX_CONCURRENCY`, `AI_JOB_ENABLED=true`, `AI_AUTO_START_WORKER=false`. Полный список — `.env.example` и AI docs.

По умолчанию provider должен оставаться loopback-local. Переключение реальных транскриптов на внешнее облачное API требует отдельного осознанного разрешения; `LLM_ALLOW_REMOTE` нельзя включать автоматически. Для Ollama/vLLM на той же машине используются локальные адреса; inference endpoint публично не экспонируется.

## Persistence и proxy

SQLite и sidecar WAL/SHM должны находиться на одном persistent volume. Бэкап выполнять SQLite backup API/консистентным snapshot, не копированием живого единственного файла. Проверить restore на отдельной базе и upgrade всех миграций. Не выполнять downgrade на рабочей базе. Секреты и клиентские данные не входят в image/Git.

Reverse proxy должен обеспечивать HTTPS, same-origin `/api` → localhost:8000, static frontend, upload limit не меньше настроенного backend, разумный timeout импорта. AI job endpoints асинхронные, долгий inference не требует длинного пользовательского HTTP-соединения. Не кешировать приватные API-ответы. Не логировать тела, Authorization, подписанные URL, транскрипты. Логи proxy для API лучше ограничить безопасными шаблонами маршрутов.

В приложении нет авторизации по условиям хакатона. До публичного доступа нужны инфраструктурные ограничения (VPN/allowlist или аутентифицирующий proxy), защита Swagger, CORS и CSP под выбранную схему. CORS сам по себе не является авторизацией. Настройки proxy, сертификаты, контейнеры и процесс-supervision предстоит реализовать и проверить в Stage 4.

## Health и приёмка

- `/api/health` — backend/SQLite/schema.
- `/api/ai/health` — раздельные provider и worker; offline AI не ломает Stage 1 API.
- `/docs`, `/openapi.json` — контракт для локальной проверки.
- UI: dataset import → batch → реальные terminal статусы → Evaluation → evidence → appeal → version activation → pinned reevaluation.

Нерешённый аппаратный блокер Stage 2: локальная GTX 1660 Ti потеряла связь с драйвером (NVIDIA Xid 79), CPU inference слишком медленный. Stage 3 не меняет драйверы, модель, GPU и не запускает worker.

На исправной GPU ещё требуется закончить реальные Qwen RU/KZ/EN, длинный разговор и voice-transcript проверки, grounded evidence, качество (включая KZ), latency, restart/recovery и доступный batch. В рабочей базе сохранена одна настоящая AI Evaluation; остальные queued/failed/cancelled не являются результатами. Не создавать тег Stage 2 Complete до выполнения её критериев. Возможность обработки 65 заданий проверена в Stage 3 через реальную очередь на синтетической базе без inference.
