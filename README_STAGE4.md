# Stage 4 — Deployment preparation / PARTIAL

Проверено локально **8 ноября 2026**. Развёртывание на RunPod **не выполнено**: SSH Agent не содержит ключа; BatchMode-подключение отклонено `Permission denied (publickey)`. GPU, persistent mount, exposed ports, внешний HTTPS и lifecycle Pod пока не проверены. Production URL не выдан. Stage 2 остаётся PARTIAL; `stage-2-ai-complete` и `stage-4-runpod-ready` не созданы.

## Что реализовано и проверено

- Конфигурации Nginx и Supervisor без секретов; генератор `scripts/production_config.py`.
- Аутентификация перед UI, API, импортом, Swagger и OpenAPI; no-store, CSP, отсутствие access logs и пересылки Basic credentials в FastAPI.
- Запуск сервисов от непривилегированного пользователя; FastAPI и Ollama только на loopback; отдельный worker; приватный Unix socket Supervisor.
- Backend env читается как данные, без shell expansion. Уже существующие env и credentials не перезаписываются.
- SQLite Backup API, integrity/FK checks, SHA256 по таблицам и файлу, проверка восстановления во временную копию, retention 48 snapshots.
- Supervisor event listener для backup раз в час. Worker autostart выключен до аудита перенесённой очереди; затем включается конфигурацией.
- `production_healthcheck.py`: backend/provider/worker отдельно, состояния очереди, место на диске, проверка отказа без пароля. Ошибка возвращает ненулевой exit code.
- Локальный TLS/Nginx smoke с production React build и отдельной синтетической SQLite: защищены 7 маршрутов; импорт → новая версия → ручная test evaluation → апелляция → пересчёт 81.88 → 88.13. Браузер проверил 10 маршрутов, evidence, mobile и Swagger.
- Реальный локальный Supervisor 4.3.0: SIGKILL API, восстановление API без остановки worker; SIGKILL idle worker, новый worker после истечения lease; автоматический backup и restore. Это **не проверка рестарта RunPod или GPU inference**.

## Результаты

| Проверка | Результат |
|---|---|
| Pytest | 279 passed, 0 failed |
| Ruff | Passed |
| Alembic check | No new upgrade operations detected |
| Frontend Vitest | 65 passed |
| Playwright E2E | 16 passed, synthetic SQLite |
| ESLint / Vite production build | Passed |
| Protected proxy / browser smoke | Passed locally, test certificate |
| Supervisor recovery / scheduled backup | Passed locally |
| RunPod inference / live external smoke | Не выполнены: SSH недоступен |

Исходная локальная БД: **65 conversations, 1268 messages, 1 evaluation, 9 jobs, 6 attempts**, 8 критериев, одна версия. Консистентная локальная копия восстановлена и проверена по всем 16 таблицам. Реальная база, секретный API URL и транскрипты не передавались на RunPod. В рабочей базе не запускались новые AI jobs.

## Что необходимо для продолжения

1. Добавить ключ в доступный агент. В текущем сеансе агент слушает `/run/user/1000/cqa-ssh-agent.sock`; выполнить **в локальном терминале**, парольную фразу не отправлять в чат:
   ```bash
   SSH_AUTH_SOCK=/run/user/1000/cqa-ssh-agent.sock ssh-add ~/.ssh/runpod_cqa
   ```
2. Подтвердить допустимость обработки DEV на этом RunPod по условиям организаторов/владельца данных. До подтверждения использовать только синтетические данные.
3. После SSH проверить Pod/GPU/mount/ports, выбрать модель по VRAM, настроить startup без нарушения Jupyter, проверить protected HTTPS извне.
4. Пройти реальные RU/KZ/EN/long/voice inference, benchmark, изменение критерия, batch, restart, transfer/restore (если разрешены). Только затем фиксировать Ready tags.

## Документы и команды

- [Развёртывание](docs/runpod-deployment.md)
- [Архитектура](docs/production-architecture.md)
- [Защита](docs/production-security.md)
- [Эксплуатация](docs/production-operations.md)
- [Backup/restore](docs/production-backup.md)
- [Контрольный набор и стоп-код](docs/control-dataset-runbook.md)
- [Пятиминутная защита](docs/hackathon-final-demo.md)

Из корня проекта, без доступа к RunPod:

```bash
uv run --directory backend pytest
uv run --directory backend ruff check . ../scripts
cd frontend
npm ci
npm run lint
VITE_API_BASE_URL=/api VITE_DEMO_MODE=false npm run build
npm run test
npm run test:e2e
cd ..
uv run --directory backend python ../scripts/test_production_proxy.py
uv run --directory backend python ../scripts/test_production_supervision.py
```

Последние две команды требуют свободный localhost:8000. Proxy test требует локальный Docker и Chromium Playwright; используется закреплённый digest официального Nginx image. Supervision test использует `uvx` и Supervisor 4.3.0. Стенды сами закрывают свои процессы/контейнеры и удаляют временные данные. Ollama не запускают. Docker на RunPod не требуется.
