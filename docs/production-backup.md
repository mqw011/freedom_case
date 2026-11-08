# SQLite backup and restore

`scripts/production_backup.py` использует SQLite Backup API и включает committed WAL pages, если БД работает в WAL. Активную базу не копируют одиночным `cp`. Snapshot создаётся эксклюзивно с mode0600; частичный файл удаляется при ошибке. Проверяются integrity_check и foreign_key_check, в manifest сохраняются SHA256 файла, hashes/числа строк всех таблиц и alembic revisions. Тексты строк в manifest не сохраняются.

```bash
python3 scripts/production_backup.py backup \
  --database "$CQA_ROOT/data/cqa.db" --directory "$CQA_ROOT/backups" --keep 48
python3 scripts/production_backup.py verify-restore --backup "$CQA_SNAPSHOT"
python3 scripts/production_backup.py inspect --database "$CQA_SNAPSHOT"
```

`CQA_SNAPSHOT` — существующий путь, возвращённый backup. Restore test создаёт отдельный временный файл и сверяет все таблицы; рабочую БД не открывает на запись. Для переноса допустимо `snapshot(source, new_destination)` из модуля: назначение обязано не существовать. Никакого overwrite production по умолчанию нет.

Supervisor слушает `TICK_3600`, выполняя backup примерно каждый час своего uptime. Хранятся последние 48 успешных snapshots с manifest; чужие файлы не удаляются. При сбое listener пишет безопасный `backup_failed` и продолжает принимать события. Отдельный backup перед обновлением/переносом/freeze обязателен. [Supervisor events](https://www.supervisord.org/events.html).

Все копии находятся на приватном persistent storage. Это защищает от логических ошибок/сбоев приложения, но **не заменяет независимую копию при потере самого volume**. После разрешения обработки данных забрать проверенный snapshot через SSH в защищённое локальное хранилище владельца. Публичный bucket не используется.

Для восстановления реального сервиса: остановить writers; сохранить текущую БД отдельным snapshot; проверить выбранную копию в отдельном каталоге; сравнить SHA256, revision и counts; только затем согласованно переключить database path/файл, сохраняя прежнюю БД. Не применять downgrade. Запустить API/worker после аудита queued jobs и lease.

## Фактическая проверка 2026-11-08

Локальная DEV-копия успешно восстановлена: 16 таблиц, 65 conversations, 1268 messages,
1 evaluation, 9 jobs, 6 attempts, 8 criteria. После разрешения владельца она передана
по SSH на подтверждённый network volume; файл и fingerprints всех таблиц совпали.
На RunPod дополнительно создан snapshot `cqa-20261108T030432822046Z-182d1546.sqlite3`:
restore во временную копию, integrity/FK и все 16 таблиц проверены успешно.
Создана и отдельно восстановлена также копия `cqa-20261108T035120049641Z-e02f539a.sqlite3`
с 79 conversations,1327 messages,7 evaluations,29 jobs. Она передана обратно по SSH
в локальный игнорируемый `backend/data/stage4-backups/runpod/` (0600), где повторно
прошла restore/integrity/FK проверку всех16 таблиц. Перед freeze создаётся свежая копия.

Scheduled backup проверен локально через настоящий Supervisor с ускоренным тестовым
событием. На RunPod listener с настоящим TICK_3600 выполнил два backup события; в том числе
создан `cqa-20261108T040000853328Z-5b392b07.sqlite3`. Retention — 48 копий.
FUSE mount игнорирует mode0600: защита данных опирается на приватность volume/account,
а не на chmod. См. [ограничения безопасности](production-security.md).

Финальный проверенный snapshot при сдаче: `cqa-20261108T044445147310Z-eed59c86.sqlite3`.
В нём34 evaluations,106 jobs,48 attempts,7 checklist versions,5 appeals/decisions;
16таблиц прошли restore/integrity/FK как на Pod, так и после SSH-копирования в
локальный `backend/data/stage4-backups/runpod/` mode0600. DEV65/1268 сохранены.
Это снимок на04:44:45UTC; работающий worker создаёт последующие результаты.
