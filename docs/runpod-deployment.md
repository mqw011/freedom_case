# RunPod deployment

Проверено 2026-11-08 на существующем Pod `f05y0qgekhw7ag`. Новый Pod не создавался.
Вход: https://f05y0qgekhw7ag-8080.proxy.runpod.net (HTTPS + Basic Auth).

## Фактическое окружение

- NVIDIA RTX 4090, 24564 MiB VRAM; драйвер 595.91.07, CUDA 13.2.
- Ubuntu 24.04.5; memory cgroup 124999999488 bytes, CPU quota 31.125 cores.
- Network volume `te2bym73hq` смонтирован в `/workspace` через RunPod FUSE.
- Container overlay 100 GB временный. `df` network volume показывает общий pool,
  а не подтверждённую квоту аккаунта; квоту нужно смотреть в Console.
- Python 3.12.15 (uv managed), uv 0.13.4, Node 24.22.2, Supervisor 4.3.0,
  Ollama 0.40.15. Зависимости приложения установлены из `uv.lock` и `package-lock.json`.
- Модель `qwen3:14b`, Q4_K_M, 9.3 GB; native Ollama API. Драйверы не менялись.

Mount подтверждён через `findmnt`, а не по одному имени `/workspace`.
[RunPod storage lifecycle](https://docs.runpod.io/pods/storage/types).
SQLite DELETE journal прошёл проверку межпроцессных блокировок и конкурентных commits.
WAL на этом сетевом mount не включать. [SQLite WAL](https://www.sqlite.org/wal.html).

## Каталоги и секреты

`/workspace/cqa`: `releases/<full SHA>/`, `data/cqa.db`, `models/`, `backups/`,
`logs/`, `config/`, `tools/`, `python/`, `secrets.vault`, `bootstrap.sh`.
Текущий checkout указан в `config/runtime.json`.

FUSE не применяет chmod/chown. Поэтому `secrets` и `run` — ссылки в приватный
`/run/cqa`; там настоящий mode0700/0600. Секреты переносятся между запусками только
в AES-256-GCM vault. Ключ отсутствует на network volume и в Git. База и backups
защищены приватностью RunPod volume/account; шифрование базы приложением не реализовано.
См. [security](production-security.md).

Сервисный пользователь `cqa` UID2001. Root нужен только bootstrap/admin;
API, worker, Ollama, CQA nginx и backup listener работают от `cqa`.

## Доступ и обновление

Приватный SSH-ключ остаётся на CachyOS и разблокируется SSH Agent.
Gateway требует PTY. Direct TCP SSH IP/порт меняются после Console reset —
проверять Connect/gateway и fingerprint, не отключать проверку host key.

При обновлении создать новый checkout на **фиксированном SHA**, не менять файлы
работающего release. От service user, с уже установленными инструментами:

```bash
export CQA_ROOT=/workspace/cqa
# Указать полный SHA проверенного коммита:
export CQA_RELEASE="$CQA_ROOT/releases/$CQA_SHA"
export PATH="$CQA_ROOT/tools/node/bin:$CQA_ROOT/tools/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin"
export UV_PYTHON_INSTALL_DIR="$CQA_ROOT/python"
export UV_CACHE_DIR="$CQA_ROOT/cache"
export UV_LINK_MODE=copy
git clone https://github.com/mqw011/freedom_case.git "$CQA_RELEASE"
git -C "$CQA_RELEASE" checkout --detach "$CQA_SHA"
uv sync --directory "$CQA_RELEASE/backend" --locked --python 3.12
cd "$CQA_RELEASE/frontend"
npm ci
VITE_API_BASE_URL=/api VITE_DEMO_MODE=false npm run build
```

Перед переключением остановить worker штатно и сделать Backup API snapshot.
Не копировать активную SQLite одиночным `cp`. Перенос исходного DEV выполнен с
разрешения владельца, по SSH, с проверкой SHA256 и всех 16 таблиц.

```bash
cd "$CQA_RELEASE"
python3 scripts/production_config.py render \
  --root "$CQA_ROOT" --release "$CQA_RELEASE" \
  --host f05y0qgekhw7ag-8080.proxy.runpod.net \
  --model qwen3:14b --port 8080 --api-port 18000 \
  --nginx /usr/sbin/nginx --ollama "$CQA_ROOT/tools/bin/ollama" --enable-worker
"$CQA_RELEASE/backend/.venv/bin/python" scripts/production_service.py --root "$CQA_ROOT" migrate
"$CQA_RELEASE/backend/.venv/bin/python" scripts/production_service.py --root "$CQA_ROOT" check
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" reread
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" update
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" signal HUP proxy
```

Генератор не переписывает backend.env или пароль. `--enable-worker` применять только
после аудита очереди. Смена env не переписывает параметры уже созданных jobs.
При изменении секретов требуется повторный `production_vault.py seal`, иначе будущий
bootstrap восстановит прежний env. Ключ передавать через mode0600 файл или защищённую
переменную, никогда аргументом со значением и никогда через shell `source`.

## Порты и сохранённые сервисы

- HTTP8080 открыт в RunPod proxy; HTTP8888 Jupyter сохранён.
- FastAPI слушает **127.0.0.1:18000**, Ollama **127.0.0.1:11434**.
- Порт 8000 намеренно не используется: образ содержит существующий proxy 8001 → 8000.
- Не открывать 8080 как Direct TCP: HTTPS терминируется RunPod proxy, CQA nginx доверяет
  forwarded-proto только в этой топологии.
- Штатные `/start.sh`, nginx и Jupyter не заменяются; Jupyter имеет отдельную аутентификацию.

[RunPod HTTP ports](https://docs.runpod.io/pods/configuration/expose-ports).
Провайдер ограничивает длительность HTTP-запроса; AI API быстро возвращает job ID,
долгий inference выполняет отдельный worker.

## Lifecycle — отложен владельцем

Supervisor работает без открытого SSH и восстанавливает дочерние сервисы.
**Автоматическое восстановление всего приложения после restart/redeploy Pod пока
не активировано и не считается проверенным.** Владелец попросил отложить этот пункт.

Для завершения позже: Start Command `/bin/bash /workspace/cqa/bootstrap.sh` и
`CQA_VAULT_KEY` в защищённых переменных Pod. Значение ключа хранится у владельца
в локальном mode0600 файле, не в документации. Затем сделать backup и реальный restart test.

До настройки автозапуска после Pod reset нужен ручной bootstrap: передать локальный
ключ по SSH в `/run/cqa-vault-key` mode0600, выполнить от root:

```bash
CQA_RELEASE=$(python3 -c 'import json; print(json.load(open("/workspace/cqa/config/runtime.json"))["release"])')
"$CQA_RELEASE/backend/.venv/bin/python" "$CQA_RELEASE/scripts/production_bootstrap.py" \
  --root /workspace/cqa --key-file /run/cqa-vault-key --start-services-only
```

Команда восстанавливает приватный runtime и Supervisor; уже работающий Jupyter не
перезапускает. Не удалять persistent vault или базу. Rollback приложения не откатывает БД.
Финальные фактические результаты: [Stage 4 report](../README_STAGE4.md).
