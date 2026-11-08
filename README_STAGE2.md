# Stage 2 — AI Evaluation Engine

**Статус: PARTIAL.** Backend, очередь и автоматические проверки реализованы. Обязательная проверка качества и успешный real inference на всех целевых типах диалогов пока не завершены: локальная GPU отказала (NVIDIA Xid 79), полноценный запрос на CPU превысил 600 секунд. Тег `stage-2-ai-complete` не создан.

Реализован путь **Conversation → Qwen3/Ollama → StructuredEvaluation → grounding + semantic audit → EvaluationService → Scoring Engine → SQLite → REST API**. Полноценный React UI — Stage 3, RunPod deployment — Stage 4.

Архитектура и настройки: [AI engine](docs/ai-engine.md). Очередь, отмена, recovery и API: [AI jobs](docs/ai-jobs.md). Измерения: [качество](docs/ai-evaluation-quality.md).

## Запуск на CachyOS

Рабочий каталог проекта: `/home/wrld/Documents/freedom_case`. Python устанавливается в venv через uv; системный Python и видеодрайверы не изменяются. Существующие `.env` и SQLite сохраняются.

```bash
cd /home/wrld/Documents/freedom_case/backend
uv sync --locked --python 3.12
uv run alembic upgrade head
```

### Ollama

В проверенном окружении уже был установлен `/usr/local/bin/ollama` версии 0.13.5. Проверить наличие сервиса/модели перед запуском:

```bash
command -v ollama
ollama --version
ollama list
ollama ps
```

Если Ollama отсутствует, используйте [официальную установку для Linux](https://docs.ollama.com/linux); она не выполнялась повторно на проверяемой машине. Установку/обновление GPU-драйверов не следует смешивать с установкой приложения.

В отдельном терминале, если порт 11434 свободен:

```bash
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 ollama serve
```

Однократная загрузка **одной** модели, если `ollama list` ещё не показывает её:

```bash
ollama pull qwen3:4b
```

При недоступной GPU можно запустить тот же Ollama на CPU, предварительно остановив свой прежний процесс Ollama:

```bash
CUDA_VISIBLE_DEVICES=-1 OLLAMA_VULKAN=0 \
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 ollama serve
```

Это настройка процесса; драйверы не меняются. [Официальное описание CPU fallback](https://docs.ollama.com/gpu). Не запускайте второй сервер на занятом порту.

### Backend, worker, frontend

Терминал backend:

```bash
cd /home/wrld/Documents/freedom_case/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Терминал worker:

```bash
cd /home/wrld/Documents/freedom_case/backend
uv run python -m app.ai.worker
```

На CPU можно увеличить timeout и контекст **перед постановкой новых jobs**, не меняя `.env`:

```bash
LLM_TIMEOUT=600 LLM_CONTEXT_LENGTH=24576 LLM_MAX_OUTPUT_TOKENS=2048 \
  LLM_MAX_RETRIES=0 uv run uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --no-access-log
```

Это альтернативный запуск backend, не второй процесс. Параметры закрепляются в создаваемых jobs; worker подхватывает их из БД. Большой контекст требует дополнительной RAM. Для обычной GPU конфигурации default context 16384; он был размещён на GTX 1660 Ti 6 ГБ целиком.

Терминал frontend:

```bash
cd /home/wrld/Documents/freedom_case/frontend
npm ci
npm run dev
```

Swagger: http://127.0.0.1:8000/docs. Backend health: `/api/health`; provider/worker health: `/api/ai/health`. Доступ только через loopback; Ollama нельзя открывать публично.

## Управление через CLI

Из backend. Идентификаторы заменяйте на фактически полученные; без ключа запрос означает новую явную оценку.

```bash
uv run python -m app.cli.ai health
uv run python -m app.cli.ai evaluate 1 --key local-demo-1
uv run python -m app.cli.ai job 1
uv run python -m app.cli.ai evaluation 1
uv run python -m app.cli.ai batch --dataset 1 --key local-dev-batch-1
uv run python -m app.cli.ai progress 1
uv run python -m app.cli.ai retry 1
uv run python -m app.cli.ai retry-failed 1
uv run python -m app.cli.ai cancel 1
```

Retry предназначен только для failed; cancel — queued/running. `evaluation` намеренно показывает подробный результат локальному оператору, поэтому его вывод может содержать цитаты и не должен публиковаться. Остальные команды возвращают безопасные job/batch DTO.

Для ограниченной обработки очереди:

```bash
uv run python -m app.ai.worker --once
uv run python -m app.ai.worker --max-jobs 3
```

## Тесты и benchmark

Автоматические тесты не обращаются к Ollama или DEV API:

```bash
cd /home/wrld/Documents/freedom_case/backend
uv run pytest
uv run ruff check .
uv run alembic check
cd ../frontend
npm ci
npm run lint
npm run build
```

Отдельный **настоящий** benchmark использует публичные синтетические кейсы и не создаёт фиктивных DEV Evaluations:

```bash
cd /home/wrld/Documents/freedom_case/backend
uv run python -m app.ai.benchmark --case ru_good
uv run python -m app.ai.benchmark
```

Для CPU: `LLM_TIMEOUT=600 LLM_CONTEXT_LENGTH=24576 LLM_MAX_OUTPUT_TOKENS=2048 LLM_MAX_RETRIES=0` перед той же командой. Benchmark запускайте при остановленном worker, чтобы не конкурировать за локальную модель. По умолчанию агрегаты сохраняются в игнорируемый `data/ai-verification/benchmark.json`; `--output` позволяет выбрать другой путь. В отчёт не входят реальные диалоги или raw responses.

## Stage 3 и будущий RunPod

Frontend-клиент готов: `frontend/src/api/ai.js`, DTO описаны в [ai-jobs.md](docs/ai-jobs.md). Результаты и апелляции используют Stage 1 API без несовместимых изменений. Статус failed не является оценкой 0; needs_human_review должен быть видимым UI-состоянием.

Для RunPod настроить provider/base URL/model/context/concurrency/timeouts, отдельные процессы API и worker, persistent volume для SQLite и секретов, HTTPS и инфраструктурную защиту. OpenAI-compatible transport не требует изменения Scoring Engine. Реальные данные нельзя отправлять внешнему серверу без отдельного разрешения владельца.

## Фактическая проверка

Окончательные результаты real inference, benchmark, regression и состояния очереди приводятся в [ai-evaluation-quality.md](docs/ai-evaluation-quality.md). Наличие валидного JSON само по себе не означает хорошего качества оценивания.

## Проверка Stage 4 — 2026-11-08

RunPod inference пока не выполнен: SSH Agent ещё не содержит разблокированного ключа. Новые метрики GPU/качества не получены; прежний статус Stage 2 **PARTIAL** сохраняется. Локальные proxy, backup и UI-тесты не заменяют проверку Qwen. См. [Stage 4](README_STAGE4.md).
