# Production security

**Внешняя защита проверена на RunPod 2026-11-08.** HTTPS с действительным сертификатом
и Basic Auth работает на `f05y0qgekhw7ag-8080.proxy.runpod.net`. Запросы без входа
к UI, API, import, Swagger/OpenAPI отклоняются. Дополнительно локальный nginx/TLS
тест проверяет CSRF и все 7 маршрутов, включая Redoc и POST импорта.

## Границы доступа

Nginx применяет Basic Auth на уровне server ко всему приложению. Пароль генерируется криптографически, 32 случайных байта; в htpasswd хранится salted SHA512 crypt. Открытая копия для передачи владельцу — только `secrets/access.json` mode0600. Генератор никогда не печатает её и не перезаписывает существующие credentials. Basic Auth пригоден для ограниченной демонстрации, но не даёт пользовательские роли и индивидуальный аудит действий.

Изменяющие состояние запросы с чужим Origin или Sec-Fetch-Site=cross-site отклоняются: браузер может кэшировать Basic Auth. API-клиенты без Origin по-прежнему обязаны пройти аутентификацию.

Credentials передавать владельцу/жюри через согласованный защищённый канал или локальный password manager. Не отправлять их в отчёты, URL, frontend, Git или shell arguments. Browser Basic Auth кэширует вход; для общего компьютера использовать отдельное приватное окно и закрыть его после показа.

API:18000 и Ollama:11434 слушают loopback. Порт API выбран отдельно от штатного
незащищённого proxy образа 8001 → 8000. Supervisor доступен через Unix socket0700
в `/run/cqa/state`. Порт 8080 открыт через HTTP proxy; **не открывать его через Direct TCP**.
Nginx считает X-Forwarded-Proto доверенным только внутри этой топологии.
Jupyter:8888 сохранён с включённой штатной аутентификацией; его credentials независимы от CQA.

Все ответы no-store; access log выключен, request bodies не пишутся. Заголовок Authorization удаляется перед FastAPI. CSP приложения допускает scripts только своего origin; для защищённых Swagger/Redoc разрешены их штатные CDN bundles. Документация требует доступности этих CDN; клиентские транскрипты не передаются туда приложением. Inline styles нужны динамическим графикам. Referrer-Policy=no-referrer защищает переходы к подписанным аудиоссылкам.

## Секреты и реальные данные

- Backend env читается dotenv без interpolation и без shell source. Power Automate `sig` остаётся только на backend.
- Владелец явно подтвердил допустимость обработки DEV на этом RunPod. Консистентная
  SQLite-копия передана по SSH после подтверждения network volume и проверена по всем таблицам.
- Копировать SQLite только через Backup API и зашифрованный SSH, после подтверждения постоянного хранилища.
- Не использовать публичные buckets, telemetry, сырые prompts/LLM responses и клиентские тексты в диагностике.
- На фактическом FUSE volume chmod/chown не действуют. Plaintext secrets находятся
  на POSIX runtime `/run/cqa/secrets` с 0700/0600; ссылки `root/secrets` и `root/run`
  ведут в runtime. В persistent `secrets.vault` лежат только зашифрованные данные
  AES-256-GCM с аутентификацией. Случайный 256-bit ключ не хранится на volume.
- SQLite и backup на volume не зашифрованы приложением. Их конфиденциальность зависит
  от приватности RunPod volume/account. Нельзя предоставлять посторонним shell-доступ к Pod
  или подключать этот volume к чужим workload. POSIX isolation на этом mount не заявляется.
- Ключ vault хранится у владельца в локальном файле mode0600. Для будущего автозапуска
  предусмотрена переменная RunPod `CQA_VAULT_KEY`; её настройка отложена пользователем.
  Bootstrap удаляет ключ из environment перед штатным startup; дочерние CQA-сервисы
  получают только ограниченный whitelist переменных. Raw prompts и responses не логируются.

## Проверка извне

```bash
python3 scripts/production_healthcheck.py \
  --base-url "https://$CQA_HOST" --credentials-file /private/path/access.json --require-ai
```

Команда требует HTTPS с валидным сертификатом, не следует redirect с credentials, отдельно проверяет те же URL без auth. Nonzero означает провал. Кроме неё проверить панель exposed ports и реальные внешние TCP mappings: один отказ `/` не доказывает отсутствие обхода.

Ollama запускается с `OLLAMA_NO_CLOUD=1`; cloud inference и web search отключены на
уровне локального сервиса, дополнительно к запрету внешнего LLM endpoint в приложении.
[Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
