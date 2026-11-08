# RunPod deployment procedure

**Статус: локально проверенный инструментарий, remote deployment ожидает SSH.** Ниже процедура для существующего Pod, а не утверждение о выполненных серверных командах. Не создавайте новый платный Pod.

## 1. Доступ и preflight

Приватный ключ остаётся на CachyOS. Разблокируйте его через `ssh-add` в локальном терминале. Затем используйте BatchMode/IdentitiesOnly и текущий gateway из задачи. Если gateway не поддерживает exec/SCP, используйте интерактивный SSH или актуальный Direct TCP SSH из Connect; не угадывайте IP/порт.

На Pod проверить `nvidia-smi`, `/etc/os-release`, `uname -a`, `free -h`, `df -h`, `lsblk`, `findmnt`, `ss -ltnp`, Python/uv, Node/npm, Git/curl, supervisor/nginx и существующий startup/Jupyter. Не печатать весь environment и командные строки с Jupyter tokens. Jupyter:8888 оставить на месте и проверить его защиту.

Подтвердить mount **по настройкам Pod и `findmnt`**, включая поведение при stop/restart и удалении. Container disk нельзя считать постоянным. Volume disk и network volume имеют разный lifecycle; название `/workspace` само по себе не является доказательством. [RunPod storage](https://docs.runpod.io/pods/storage/types).

Текущий backend не включает WAL принудительно. Для SQLite нужна проверенная POSIX-блокировка на выбранном mount и один host. Не включать WAL на сетевой ФС автоматически. Сначала проверить конкурентные операции и backup на синтетической копии. [SQLite WAL](https://www.sqlite.org/wal.html).

## 2. Постоянные пути и непривилегированный пользователь

Дальнейшие переменные задаются **фактическими значениями после preflight**, а не путями из примера:

- `CQA_ROOT`: отдельный каталог на подтверждённом persistent mount.
- `CQA_SHA`: полный SHA проверенного release commit.
- `CQA_RELEASE`: `$CQA_ROOT/releases/<full-git-sha>`.
- `CQA_HOST`: подтверждённый HTTP proxy hostname из RunPod Connect, без scheme/path.
- `CQA_MODEL`: модель, выбранная после измерения GPU; 14B — предпочтение, не уже выбранный результат.

Структура: `releases/`, `data/cqa.db`, `secrets/backend.env`, `secrets/access.json`, `secrets/access.htpasswd`, `models/`, `backups/`, `logs/`, `config/`, `run/`, `tools/`, `python/`.

Создать отдельного непривилегированного service user с доступом к GPU device nodes и владением **только новым каталогом CQA**. Не делать `chown -R` всего общего mount. Каталоги 0700, секреты 0600. Launcher откажется запускать приложение от root.

## 3. Зависимости и release

Установить nginx, OpenSSL и uv способом, подходящим проверенному образу Pod. Systemd и Docker-in-Docker не требуются. Python/uv tools держать на persistent storage; бинарники OS из ephemeral слоя должны восстанавливаться штатным startup, не через ручной SSH при каждом старте. Конкретный lifecycle пока не проверен.

От имени service user, после установки uv/Git/Node ≥22.12:

```bash
export UV_PYTHON_INSTALL_DIR="$CQA_ROOT/python"
export UV_CACHE_DIR="$CQA_ROOT/cache"
export UV_TOOL_DIR="$CQA_ROOT/tools/uv"
export UV_TOOL_BIN_DIR="$CQA_ROOT/tools/bin"
git clone https://github.com/mqw011/freedom_case.git "$CQA_RELEASE"
git -C "$CQA_RELEASE" checkout --detach "$CQA_SHA"
uv sync --directory "$CQA_RELEASE/backend" --locked --python 3.12
uv tool install 'supervisor==4.3.0'
cd "$CQA_RELEASE/frontend"
npm ci
VITE_API_BASE_URL=/api VITE_DEMO_MODE=false npm run build
```

`CQA_SHA` — точный проверенный commit; не использовать движущийся `main` как идентификатор deployment. При приватном репозитории передать release artifact через SSH, без личного ключа на Pod.

## 4. Конфигурация, БД, вход

Следующие команды реализованы и проверены локально; значения Pod ещё не определены:

```bash
cd "$CQA_RELEASE"
python3 scripts/production_config.py render \
  --root "$CQA_ROOT" --release "$CQA_RELEASE" --host "$CQA_HOST" \
  --model "$CQA_MODEL" --port 8080 \
  --nginx /usr/sbin/nginx --ollama "$CQA_ROOT/tools/bin/ollama"
python3 scripts/production_config.py credentials --root "$CQA_ROOT"
"$CQA_RELEASE/backend/.venv/bin/python" scripts/production_service.py --root "$CQA_ROOT" migrate
"$CQA_RELEASE/backend/.venv/bin/python" scripts/production_service.py --root "$CQA_ROOT" check
nginx -t -c "$CQA_ROOT/config/nginx.conf"
"$CQA_ROOT/tools/bin/supervisord" -c "$CQA_ROOT/config/supervisord.conf"
"$CQA_ROOT/tools/bin/supervisorctl" -c "$CQA_ROOT/config/supervisord.conf" status
```

Пути nginx/mime.types/ollama уточнить по preflight. Генератор НЕ переписывает backend.env и credentials. Первый запуск — пустая мигрированная SQLite и явный импорт синтетического JSON. Настоящий DEV и organizer URL разрешены только после подтверждения обработки данных. Миграции существующей БД выполнять после backup. Старые queued jobs сначала аудировать: они содержат закреплённые модели/версии/config, смена LLM_MODEL их не перепишет.

Ollama установить по [официальной Linux инструкции](https://docs.ollama.com/linux), без изменения NVIDIA driver. Бинарники/модели сохранять в persistent paths. Проверить `ollama ps` и `nvidia-smi`: наличие модели на диске не означает GPU inference. Подбирать context/output/timeout на измерениях. Не скачивать сразу несколько моделей.

После аудита очереди повторить `render` с `--enable-worker`, выполнить `supervisorctl reread` и `supervisorctl update`. AI_AUTO_START_WORKER остаётся false; отдельный worker autostart=true. При изменении env перезапускать нужные сервисы через Supervisor.

## 5. HTTP proxy и lifecycle

Порт 8080 — пример свободного HTTP-порта; подтвердить его в Expose HTTP Ports. Не добавлять 8000/11434 или proxy:8080 в Direct TCP. HTTP proxy формирует HTTPS URL; доступ публичный, поэтому поверх него обязателен Nginx Basic Auth. Проверить фактический `X-Forwarded-Proto: https`; без него конфигурация перенаправляет на HTTPS. [RunPod expose ports](https://docs.runpod.io/pods/configuration/expose-ports).

Nginx доверяет forwarded proto **только при условии отсутствия публичного TCP-обхода**. Локальная подмена заголовка не является внешней TLS-защитой. Обязательно проверить внешним клиентом отказ без пароля и отсутствие bypass ports. Подключить Supervisor к существующему startup Pod, сохранив Jupyter. Это действие и полный restart Pod пока НЕ проверены и остаются условиями приёмки.

## 6. Приёмка

Защищённый внешний smoke, реальные inference/benchmark, [операции](production-operations.md), [backup/restore](production-backup.md), контрольный набор и freeze обязательны перед Ready tag. Локальный self-signed TLS тест не подтверждает сертификат RunPod.
