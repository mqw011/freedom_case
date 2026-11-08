# План следующих этапов

## Stage 1 — реализовано

Импорт API/файла, SQLite и миграции, точный seed, версии чек-листа, Decimal scoring, ручные/test результаты, evidence, апелляции с историей, тесты и React foundation. Настоящий DEV API проверен 2026-11-07: 65 диалогов и 1 268 реплик импортированы и сверены с источником. Подписанный endpoint хранится только в локальном окружении; новым установкам требуется собственная конфигурация доступа.

## Stage 2 — PARTIAL, backend реализован

Реализованы Ollama и OpenAI-compatible transport, динамические prompts, строгие DTO, grounding, semantic audit, контекстные окна, durable jobs/batches/attempts, lease recovery и CLI. Используется существующий EvaluationService и неизменённый Scoring Engine. См. [инженерный отчёт](../README_STAGE2.md), [качество и ограничения](ai-evaluation-quality.md).

Локальный блокер NVIDIA Xid79 обойдён переносом на RunPod RTX4090. Пять обязательных
DEV-сценариев RU/KZ/EN/long/voice прошли весь pipeline, выполнен синтетический benchmark.
Текущие показатели качества и окончательная приёмка — в Stage4, без заявления
безошибочности на основании одного лишь JSON.

Следующее улучшение качества — независимая экспертная разметка реальных обезличенных примеров, более мощная модель при достаточных ресурсах и сравнение по языкам; смена модели не требует переписывать scoring.

## Stage 3 — веб-приложение

Реализованы Dashboard с полными агрегатами, Conversations с глобальными фильтрами, транскрипт/evidence/аудио, версии/редактор чек-листа, апелляции и reviewer workflow, AI jobs/batches/retry/cancel, импорт group_id и JSON. Реальные API + отдельный синтетический sandbox для e2e, без фиктивных AI-оценок в DEV. [Stage 3](../README_STAGE3.md), [проверки](stage3-test-report.md).

HashRouter и относительные ассеты сохраняют возможность встраивания в Dynamics 365. Конкретные iframe/CSP/origin ограничения принимающей системы ещё предстоит проверить.

## Stage 4 — эксплуатация

На существующем Pod работают production frontend, FastAPI, Qwen3 14B/Ollama, worker,
Nginx/HTTPS/Basic Auth, Supervisor, persistent volume и backup/restore. Docker-in-Docker
не требуется. Проверены живой browser workflow, DEV import/reimport, пять DEV inference
сценариев, synthetic benchmark и recovery. Полный DEV batch запущен; фактический прогресс
и ограничения — [Stage4](../README_STAGE4.md). Автозапуск после restart Pod отложен владельцем.
Контрольный group_id ещё не выдан: механизм импорта и обработки отрепетирован на synthetic
наборе, [runbook](control-dataset-runbook.md) описывает операции без изменения кода.

При необходимости PostgreSQL: драйвер и DATABASE_URL, проверка миграций и конкурентности. SQLAlchemy-сервисы и Scoring Engine сохраняют интерфейсы. Реальные клиентские данные, записи и секреты не входят в образы и Git.
