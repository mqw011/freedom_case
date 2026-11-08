# Stage 4 — RunPod deployment / PARTIAL

Проверка 8 ноября 2026. Приложение работает на существующем Pod **f05y0qgekhw7ag**:

**https://f05y0qgekhw7ag-8080.proxy.runpod.net**

Все маршруты защищены HTTPS + Basic Auth. Credentials переданы владельцу локальным
файлом `backend/data/runpod-access/access.json` (0600, вне Git), пароль не публикуется.
Автозапуск после полного restart/redeploy Pod **отложен по указанию владельца**.
Не считать эту часть production lifecycle завершённой; Ready tag пока не создан.

## Развёрнутые компоненты

- React production build, same-origin `/api`, HashRouter, demo mode выключен.
- FastAPI `127.0.0.1:18000` — порт исключает обход через штатный proxy образа 8001 → 8000.
- Nginx ingress8080: вход для UI/API/Swagger/import, no-store, CSP, CSRF protection.
- Ollama 0.40.15, Qwen3 14B Q4_K_M, полностью GPU; 32768 context, два слота.
- Отдельный supervised AI Worker, durable SQLite jobs/attempts/lease recovery.
- Supervisor 4.3.0: API, worker, Ollama, proxy, hourly backup listener; независим от SSH.
- SQLite на network volume `/workspace`, миграция `e42da734f08d`, DELETE journal.
- Backup API snapshot + restore verification. Retention48, копии вне release directory.
- Encrypted secrets vault (AES-256-GCM), private plaintext runtime `/run/cqa`.

GPU **RTX 4090 / 24564 MiB**. Cgroup memory125 GB, CPU quota31.125 cores.
Network volume `te2bym73hq`, путь `/workspace/cqa`; не путать общий размер FUSE pool
с квотой владельца. FUSE игнорирует POSIX permissions, поэтому секреты/сокеты перенесены
в `/run/cqa`; сама БД защищена приватностью volume/account, шифрование БД не заявляется.

## Что реально проверено

- Внешний HTTPS: UI/API/docs доступны после входа, без входа401; cross-origin writes403.
- API18000/8000 и Ollama11434 не опубликованы через RunPod HTTP proxy (404).
  Jupyter8888 сохранён; `/api/sessions` без входа403.
- Перенос DEV разрешён владельцем, выполнен Backup API → SSH → integrity/FK/fingerprints.
  Исходные65 conversations,1268 messages,8 criteria,version1 и старая AI Evaluation
  после переноса и UI smoke не изменились.
- Организаторский импорт с RunPod:65 received,0 inserted,65 skipped, warnings0.
  Подписанный URL хранится только server-side, не попадает в браузер/Git.
- API smoke: отдельный `LOCAL-SMOKE-*`, импорт/reimport, transcript, immutable versions,
  test/manual evaluation81.88 → appeal →88.13; исходный балл сохранён.
- Настоящий браузер через protected HTTPS:9 маршрутов, evidence, reviewer decision
  до93.75 с сохранением initial81.88, изменение описания критерия, новая версия,
  закрепление job version, synthetic JSON import/reimport, batch.
- Responsive1440/1280/768/390,0 page errors. Production screenshots/транскрипты не публикуются.
- Отдельный локальный production proxy test:10 маршрутов, mobile/evidence/Swagger,
  отдельная синтетическая БД; локальный Supervisor crash recovery/backup test.

## AI: результаты и границы

Qwen native JSON Schema прошла RU/KZ/EN generation на GPU. Модель digest:
`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`.

Быстрый режим без reasoning выявил содержательные ошибки. Проведена корректировка
общих динамических инструкций: оценивать только действительные запросы, не выдумывать
незаданные вопросы и не переносить требования между критериями. Scoring Engine и
официальный чек-лист не менялись. Семантический audit теперь объясняет отказ, а repair
получает конкретную недоверенную критику для проверки по исходному транскрипту.

Актуальные inference настройки: temperature0.6, thinking=true, output8192,
context32768, timeout300, max_retries2, repairs2, seed42, concurrency2.
Это измеряемая конфигурация, не обещание безошибочности. Рекомендации разработчика
модели предостерегают от greedy decoding; выбранные параметры проверяются на benchmark.
[Qwen model card](https://huggingface.co/Qwen/Qwen3-14B).

Первый benchmark с reasoning: RU/KZ/EN good cases прошли все валидаторы и совпали
с разметкой по8/8, score100; длительности80.93/110.42/88.07s. Для KZ/EN понадобились
repairs. Четвёртый кейс отклонён semantic audit, что привело к улучшению feedback.
Это диагностический промежуточный прогон, **не итоговая метрика всех9 кейсов**.

Пять реальных DEV-сценариев полностью сохранены и повторно проверены независимым
read-only скриптом через HTTPS (grounding + тот же Scoring Engine):

- RU: job15 → Evaluation4, 11 реплик, 100.00, 107.935s.
- KZ: job16 → Evaluation5, 12 реплик, 100.00, 239.005s (2 repair).
- EN: job17 → Evaluation6, 12 реплик, 100.00, 65.223s.
- Длинный voice: job18 → Evaluation8, 115 реплик, 35.50, 88.5s на успешную попытку.
- Voice: job19 → Evaluation9, 45 реплик, 83.33, 104.3s на успешную попытку.
- Изменённый synthetic checklist: job20 → Evaluation7, pinned version7,
  исходный71.43; тестовая апелляция через UI дала65.00, исходные ответы не изменены.

Звонки первоначально отклонялись из-за неточных цитат. Prompt2.4 связывает message ID
и дословные фрагменты JSON Schema; повторные jobs18/19 прошли без repair.
Старые failed attempts сохранены; у каждого job только одна Evaluation.
Все указанные баллы — результат модели, **не независимая экспертная разметка**.
Через браузер проверены AI-карточки и evidence, без screenshots приватных данных.

### Выбор конфигурации по измерениям

В production возвращён prompt `cqa-2.4`: полный benchmark9/9 completed,
criterion agreement88.89%, N/A91.67%, MAE10.7322, critical recall0.5 при всего двух
положительных кейсах. Prompt2.6 дал8/9 completed и78.12% agreement; он не выбран.
Оба отчёта сохранены в `docs/benchmarks/`. Это малая диагностическая выборка,
использовавшаяся при настройке, а не независимый доказательный holdout.
Неправильные модельные выводы возможны даже после self-audit: особенно идентификация,
конфиденциальность и трактовка кратких запросов. Для ответственного использования
нужна проверка банковским QA-экспертом; JSON validity не означает semantic accuracy.

Весь DEV поставлен в batch4 (65 отдельных jobs). Обработка продолжается отдельно;
её актуальные completed/failed/queued видны в UI. Не считать постановку65 задач
доказательством65 успешных оценок. Старые jobs/attempts и оценки сохранены.

Сравнение Qwen3 30B-A3B Instruct2507 Q4_K_M:RU completed, KZ/EN failed из-за
усечённого вывода; RU5/8 совпадений. Эта конфигурация отвергнута, новая платная GPU
не создавалась. Временный model cache остаётся на диске Pod, production14B и БД —
на network volume. Полный digest/настройки и отчёт сравнения сохранены в документации.

Новые технические исправления не ослабляют validation: repair сообщает, когда для
`yes` обязательна точная quote, а healthcheck проверяет реальную запись на FUSE,
поскольку `df` показывает общий pool и не видит tenant quota.

## Снимок данных и производительности

На **2026-11-08 04:44:45 UTC** (обработка продолжается):

- DEV65 conversations/1268 messages,35RU/15KZ/15EN,60chat/5voice сохранены.
- Оценено11 различных DEV-диалогов,12 AI Evaluations с учётом переоценки;
  средний final_score последней completed оценки каждого —83.64.
- В DEV batch4:6 completed,2 running,57 queued,0 failed. Не все65 завершены.
- Во всей БД с явно synthetic UI/benchmark наборами:79 conversations,1327messages,
  34evaluations,106jobs,48attempts,7checklist versions,5appeals/decisions.
- Общая очередь:32completed,2failed,13cancelled,2running,57queued.
  Исторические failed/cancelled сохранены, не выданы за оценки0.
- Для6 завершённых DEV jobs:mean99.48s,median98.89s,12provider calls,0repairs,
  43826input/18359output tokens. Pending/failed/пауза worker в эти средние не входят.
  Это не измерение скорости всего65-пакета. На9 коротких synthetic было67.11 completed/hour;
  обработка неизвестного контрольного набора за час **не гарантируется**.
- Свежий snapshot проверен restore на Pod и локально вне volume:16таблиц, integrity/FK OK.

[Машиночитаемый снимок](docs/benchmarks/2026-11-08-runpod-acceptance.json).
Текущее состояние — [пакет4](https://f05y0qgekhw7ag-8080.proxy.runpod.net/#/ai-batches/4).
Новые результаты создаются настоящим worker на GPU, независимо от открытой вкладки.

## Регрессия

- Backend:297 passed /0 failed; новые проверки выявленного quota failure и точного repair feedback.
- Ruff / Alembic check: passed.
- Frontend: npm ci, ESLint, production build passed;65 Vitest и16 Playwright E2E passed.
- Browser live acceptance: passed; операции только над явно синтетическими записями.

## Эксплуатация и документы

- [Deployment и ручной bootstrap](docs/runpod-deployment.md)
- [Архитектура](docs/production-architecture.md)
- [Защита и ограничения mount](docs/production-security.md)
- [Операции и rollback](docs/production-operations.md)
- [Backup/restore](docs/production-backup.md)
- [Контрольный набор и стоп-код](docs/control-dataset-runbook.md)
- [Пятиминутная защита](docs/hackathon-final-demo.md)
- [Измерения качества](docs/ai-evaluation-quality.md)

Проверка внешнего состояния с локальной машины, из корня репозитория:

```bash
python3 scripts/production_healthcheck.py \
  --base-url https://f05y0qgekhw7ag-8080.proxy.runpod.net \
  --credentials-file backend/data/runpod-access/access.json --require-ai
uv run --directory backend python ../scripts/production_inference_verify.py \
  --base-url https://f05y0qgekhw7ag-8080.proxy.runpod.net \
  --credentials-file data/runpod-access/access.json --jobs-file data/runpod-stage4-jobs.json
```

Проверки кода из корня:

```bash
uv run --directory backend pytest
uv run --directory backend ruff check . ../scripts
uv run --directory backend alembic check
cd frontend
npm ci
npm run lint
VITE_API_BASE_URL=/api VITE_DEMO_MODE=false npm run build
npm run test
npm run test:e2e
```

## Оставшиеся условия приёмки

Пять обязательных DEV inference-сценариев и9-case benchmark выполнены. Открытая
проблема — содержательная надёжность: известны ошибки идентификации/конфиденциальности,
а9 синтетических кейсов не заменяют независимую экспертную приёмку. Self-audit может
пропустить неверный вывод. Поэтому Stage2/Stage4 Complete/Ready tags не создаются.

Полный65-job DEV batch продолжает работу; его конечные результаты и длительность
всего пакета ещё не получены. Автозапуск всего Pod отложен владельцем; до него restart
требует ручного bootstrap с локальным vault key. Это отдельно от работающего Supervisor.
Реальный контрольный group_id ещё не выдан; его механизм импорта проверен.
Не делать git pull или изменять программные prompts после согласованного стоп-кода.
