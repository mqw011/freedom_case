# Production operations

Remote-состояние пока неизвестно. Команды ниже используют подтверждённые при развёртывании `CQA_ROOT`, `CQA_RELEASE`, `CQA_HOST`; запускать от service user. Не применять их к локальной DEV-базе ради демонстрации.

## Сервисы и health

```bash
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" status
python3 "$CQA_RELEASE/scripts/production_healthcheck.py" --require-ai --disk "$CQA_ROOT"
"$CQA_RELEASE/backend/.venv/bin/python" "$CQA_RELEASE/scripts/production_service.py" --root "$CQA_ROOT" check
```

`production_healthcheck.py` без `--require-ai` позволяет диагностировать API, пока provider выключен; он всё равно честно возвращает provider/worker=false. С `--require-ai` их недоступность означает exit1. Неверные credentials/config означают ошибку. Не путать `completed`, `failed`, `cancelled`: только completed job имеет успешную Evaluation.

```bash
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" restart api
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" restart worker
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" stop worker
```

Не запускать ещё один `python -m app.ai.worker` параллельно Supervisor. При аварии старый lease должен истечь; Supervisor повторяет запуск, даже если worker корректно завершился из-за занятого lease. Локально проверены SIGKILL API и idle worker, scheduled backup и restore. Прерывание GPU inference и полное выключение Pod ещё предстоит проверить на RunPod.

Supervisord daemon независим от SSH-сессии; **сам по себе не обеспечивает запуск после перезапуска контейнера**. Его explicit `-c` команда должна быть включена в проверенный startup hook текущего Pod, не заменяя Jupyter. Нельзя считать это выполненным до проверки самого Pod.

## Диагностика

Логи в `$CQA_ROOT/logs`: API, worker, Ollama, proxy, supervisor, backup. Ротация 5–10MB и 3 копии. Смотреть только безопасные ID, error_code, attempts, latency, token counts. Не включать DEBUG и raw prompts. GPU — `nvidia-smi`, Ollama — `ollama ps`, диск — `df -h "$CQA_ROOT"`; при ошибке GPU сначала остановить worker, сохранить job attempts и выяснить причину. Не ставить failed=completed вручную.

В UI: **AI задания → Детали → Попытки**. Retry доступен для failed; cancellation queued/running следует текущему API. Повтор того же job не создаёт повторную Evaluation. Новая явная переоценка — отдельная job с закреплённой версией.

## Реальный benchmark и производительность

После настройки GPU и модели:

```bash
"$CQA_RELEASE/backend/.venv/bin/python" "$CQA_RELEASE/scripts/production_service.py" --root "$CQA_ROOT" benchmark
```

Команда использует защищённый env и сохраняет отдельный `data/benchmark-<UTC>.json` на persistent mount. Это 9 вручную размеченных синтетических кейсов, а не полноценная статистическая оценка реальных данных. Дополнительно пройти RU/KZ/EN, long115, voice transcript, N/A, идентификацию, грубые ошибки, изменённый критерий и переоценку через настоящие AI jobs. `voice` означает текстовый транскрипт, не анализ интонации.

Фиксировать число вызовов/repairs, actual token usage, среднее и P50/P95 при достаточной выборке, GPU VRAM и completed jobs/hour. При concurrency1 оценка throughput = 3600 / измеренное среднее wall time на диалог, включая проверки/repairs; это оценка, не гарантия. Отдельно доля failed и реальная пропускная способность batch. Сейчас RunPod latency/throughput **не измерены**. Локальный Ollama не тарифицирует API, но аренда GPU/электроэнергия не бесплатны; стоимость считать из фактического времени и тарифа владельца Pod.

## Обновление и rollback

До freeze: остановить worker, дождаться отмены/сохранения attempts; сделать Backup API snapshot; подготовить новый checkout на точном SHA, locked dependencies и production build; применить только upgrade миграций; пересоздать конфигурации с новым release; `supervisorctl reread`, `update`, проверить API, auth, worker и UI. Не менять `.env` автоматически.

При неудаче вернуть конфигурации к прежнему checkout, проверить совместимость кода с текущей схемой и перезапустить сервисы. **Не делать автоматический downgrade или restore поверх рабочей БД**: это удалило бы новые данные. Данные восстанавливаются отдельно после анализа и сохранения текущей копии.

Freeze: сохранить code SHA, deployment SHA, `uv.lock`/`package-lock.json` hashes, текущую alembic revision, точный Ollama model tag+digest, whitelist inference-настроек без секретов и DB backup. После стоп-кода не выполнять git pull и не редактировать программные prompts. Управление данными, версиями чек-листа и jobs остаётся через UI.
