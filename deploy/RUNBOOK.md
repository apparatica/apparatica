# RUNBOOK

Операции на работающем сервере. Как устроено развёртывание — [docs/deployment.md](../docs/deployment.md). Команды `just` запускаются из корня репозитория на машине оператора, остальные — на сервере под `root`. Ниже `dc` — compose текущего релиза, с его образами:

```sh
cd /opt/apparatica/current
alias dc='docker compose -f deploy/compose.yaml -f deploy/compose.server.yaml --env-file /etc/apparatica/settings.env --env-file /etc/apparatica/secrets.env --env-file release.env'
```

## Состояние

```sh
dc ps                        # сервисы и их здоровье
dc logs -f --tail 200 api    # логи сервиса (JSON, с request_id и submission_id)
readlink /opt/apparatica/current && ls -t /opt/apparatica/releases
curl -fsS https://staging.apparatica.app/api/v1/health
```

## Деплой

Каждый коммит `master` выкатывает CI (workflow Staging, [deployment.md](../docs/deployment.md#деплой-из-ci)); повторить деплой коммита — Actions → Staging → Run workflow из `master`. Вручную, с образами, собранными на хосте:

```sh
just deploy staging
```

Ручной деплой выкатывает `HEAD` машины оператора, а следующий push в `master` — снова коммит CI. Перед выкаткой на production убедитесь, что дерево чистое: имя релиза без `-dirty-` (оно печатается в задаче «Name the release»).

## Откат

```sh
ssh root@apparatica.app ls -t /opt/apparatica/releases   # сохранённые релизы, новые первыми
just rollback <релиз> staging
```

Откат снова запускает сервисы сохранённого релиза — с его образами из `release.env` — с текущими настройками и секретами и прогоняет проверки. Следующий push в `master` выкатит новый коммит поверх отката. Миграции только совместимые вперёд (specs/09 §1), поэтому схема БД не откатывается: прежний код работает с новой схемой. Релизы старше пяти последних удалены, их возвращают деплоем нужного коммита: `git switch --detach <коммит> && just deploy staging`.

## Перезапуск сервиса

```sh
dc restart api            # api, web, ingest, caddy — без потери данных
dc up -d --wait worker    # воркер доделывает текущие проверки (stop_grace_period 1m)
```

`dc down` останавливает всё, данные остаются в томах. `dc down -v` удаляет тома, то есть **все данные платформы**.

## Сертификаты

Caddy получает сертификаты Let's Encrypt при первом запросе имени и продлевает их сам. Если сайт не открывается по HTTPS:

1. DNS: `dig +short staging.apparatica.app` и `dig +short AAAA staging.apparatica.app` и остальные имена должны указывать на хост (IPv6 — адрес интерфейса, `ip -6 addr`).
2. Порты `80` и `443` открыты (`nft list table inet apparatica`): проверка Let's Encrypt идёт по ним.
3. `dc logs caddy | grep -i -E "acme|certificate|error"`. Если Let's Encrypt ограничил частоту выдачи, повтор возможен только через час и позже: не перезапускайте Caddy в цикле.

## Смена секрета

1. Удалите строку секрета из `/etc/apparatica/secrets.env`.
2. `just deploy staging`: генератор допишет новое значение, compose пересоздаст сервисы, которые его читают.
3. Сохраните новую копию файла вне сервера.

Последствия смены:

| Секрет | Что будет |
|---|---|
| `APX_GUEST_COOKIE_KEY` | гости теряют доступ к своим отправкам |
| `APX_JOB_TOKEN_KEY` | ингестор отбрасывает результаты проверок, которые уже стоят в очереди |
| `APX_CAPTCHA_KEY` | выданные задачи капчи не принимаются |
| `APX_IP_HASH_SALT` | счётчики rate limit по адресам начинаются заново |
| `VALKEY_QUEUE_*_PASSWORD` | пользователи Valkey получают новые пароли при перезапуске `valkey-queue` |
| `POSTGRES_PASSWORD` | **не меняйте так**: Postgres берёт пароль только при создании тома. Сначала `dc exec postgres psql -U apparatica -c "ALTER USER apparatica PASSWORD '<новый>'"`, затем новое значение в файл и деплой |
| `S3_<КОМПОНЕНТ>_KEY_ID` и `_SECRET` | только парой: `garage-setup` находит ключ по id и импортирует новый с правами компонента. Старый ключ остаётся в Garage с теми же правами: удалите его после деплоя (`dc exec garage /garage key delete --yes <старый id>`) |
| `GARAGE_ADMIN_TOKEN`, `GARAGE_RPC_SECRET` | Garage читает их при старте: деплой перезапускает его с новыми |
| `BACKUP_ENCRYPTION_KEY` | **не меняйте**: бэкапы, зашифрованные старым ключом, станут нечитаемыми. Если ключ скомпрометирован: новый ключ, деплой, сразу полный бэкап; старые бэкапы удалить в хранилище, когда 30 новых накопятся |
| `BACKUP_S3_KEY_ID`, `BACKUP_S3_KEY_SECRET` | не генерируются: новый ключ — у провайдера хранилища, затем в файл и деплой (Postgres перезапускается с ним), старый ключ — отозвать у провайдера |

## Бэкапы

Как устроены — [docs/backups.md](../docs/backups.md).

```sh
systemctl list-timers 'apparatica-backup*'                  # когда были и будут запуски
journalctl -u apparatica-backup -u apparatica-backup-check -n 100
dc exec -T -u postgres postgres wal-g backup-list           # полные бэкапы в хранилище
dc exec -T postgres psql -U apparatica -c 'select * from pg_stat_archiver'   # архив WAL
systemctl start apparatica-backup          # полный бэкап сейчас
systemctl start apparatica-backup-check    # проверка восстановления сейчас
grep -v '^#' /var/lib/apparatica/metrics/*.prom   # последние запуски, как их видят алерты
```

**`BackupTooOld`** (полному бэкапу больше 26 часов): в `journalctl -u apparatica-backup` — почему падает `apx-backup push`. Частые причины: хранилище (ключ, бакет, доступность), дыра в архиве WAL (`wal-verify` в конце бэкапа — см. ниже «Архив WAL не уходит»), таймер выключен (`systemctl list-timers`). После исправления — `systemctl start apparatica-backup`: удачный запуск закрывает алерт.

**`RestoreCheckFailed`** (проверка восстановления не прошла): в `journalctl -u apparatica-backup-check` — на чём остановилась `apx-backup check`: скачивание бэкапа, воспроизведение WAL, запуск Postgres или подсчёт строк. Не прочитался бэкап или WAL — это уже авария бэкапов: восстановление не гарантировано, нужен новый полный бэкап (`systemctl start apparatica-backup`) и повторная проверка. **`RestoreCheckTooOld`**: таймер `apparatica-backup-check.timer` не запускается — `systemctl list-timers`, `just deploy` его вернёт.

**Архив WAL не уходит** (`failed_count` растёт, в `dc logs postgres` ошибки `wal-push`): Postgres не удаляет неархивированный WAL, и он копится в томе `postgres`. Причины — ключ или бакет (проверьте `BACKUP_S3_*`), недоступность хранилища, отказ `WALG_PREVENT_WAL_OVERWRITE` (в префиксе архив другого кластера: новая база пишет в старые бэкапы, см. «Восстановление базы»). После исправления Postgres дошлёт накопленное сам. Если до заполнения диска не успеть — `apparatica_backups: false` и деплой выключают архив; после включения обратно сразу сделайте полный бэкап.

## Алерты

Как устроены — [docs/alerts.md](../docs/alerts.md). Сообщения приходят в чат Telegram окружения; правила бэкапов — в разделе выше. Prometheus и Alertmanager снаружи не видны: алерты и заглушки — в Grafana (Alerting), или из контейнеров:

```sh
dc --profile monitoring exec prometheus wget -qO- localhost:9090/api/v1/alerts   # что сработало
dc --profile monitoring logs --tail 50 alertmanager                             # ошибки отправки в Telegram
# пробный алерт: «Тревога» через 30 с, «Отбой» минут через 5-10
site=$(sed -n 's/^SITE_HOST=//p' /etc/apparatica/settings.env)
dc --profile monitoring exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  alert add alertname=Test "site=\"$site\"" \
  --annotation='summary="Пробный алерт"' --annotation='description="Проверка доставки."'
# заглушить известную проблему на сутки
dc --profile monitoring exec alertmanager amtool --alertmanager.url=http://localhost:9093 \
  silence add alertname=BackupTooOld --duration=24h --comment='"<почему>"'
```

**`HostMetricsMissing`** (Prometheus не получает метрики хоста): `dc --profile monitoring ps node-exporter` и его логи. Ошибка `failed to parse textfile data` — испорчен файл в `/var/lib/apparatica/metrics`: удалите его и запустите юнит его задачи (`systemctl start apparatica-backup` или `apparatica-backup-check`), он запишет новый.

**Сообщения не приходят**: в логах `alertmanager` ошибки `telegram` — неверный токен (`401`), бот не в чате или неверный id (`400 chat not found`), Telegram недоступен с хоста. Токен меняется в `secrets.env` (`TELEGRAM_BOT_TOKEN`), id — в инвентаре (`apparatica_alert_telegram_chat_id`), затем `just deploy`.

## Восстановление базы

Цель — не дольше 2 часов (NFR-REL-04). Нужны ключи из `secrets.env`: `BACKUP_ENCRYPTION_KEY` и `BACKUP_S3_KEY_*`. Восстанавливается последний полный бэкап и WAL после него — до конца архива или до момента `TIME` (UTC, например `2026-11-04 17:31:44+00`: всё, что было до него).

**На том же хосте** (испорченная база, ошибочное удаление):

```sh
dc stop caddy web api ingest worker postgres
# старые данные — в сторону, если на диске есть место (иначе пропустите)
docker volume create apparatica_postgres-before-restore
docker run --rm -v apparatica_postgres:/from:ro -v apparatica_postgres-before-restore:/to \
  "$(sed -n 's/^POSTGRES_IMAGE=//p' release.env)" cp -a /from/. /to/
dc rm -f postgres && docker volume rm apparatica_postgres
dc run --rm --no-deps -u postgres postgres apx-backup restore            # до конца архива
# или: ... apx-backup restore LATEST '<TIME>'                            # до момента
dc up -d --no-deps postgres
dc logs -f postgres     # ждать «archive recovery complete» и «ready to accept connections»
```

Затем `just deploy staging` (или `dc up -d --wait caddy valkey-queue valkey-cache ingest worker`) и сразу `systemctl start apparatica-backup`: база начала новую линию времени. Когда всё проверено, `docker volume rm apparatica_postgres-before-restore`. Для восстановления до момента нужен бэкап, сделанный раньше него: если `LATEST` новее, найдите более ранний в `wal-g backup-list` и укажите его имя вместо `LATEST`.

**На новом хосте** (хост потерян):

1. Хост в инвентаре и DNS — как в [deployment.md](../docs/deployment.md#окружения-и-хосты); `just provision <окружение> --tags host`.
2. Сохранённую копию `secrets.env` — в `/etc/apparatica/secrets.env` (`install -d -m 700 /etc/apparatica`, файл `0600`) **до первого деплоя**: генератор оставит её значения, иначе новые ключи не прочитают ни бэкапы, ни данные гостей.
3. `just deploy <окружение> -e apparatica_backups=false`: платформа с пустой базой и без архива WAL, чтобы новая база ничего не записала в префикс старых бэкапов.
4. Восстановление — как на том же хосте, начиная с `dc stop …` (копию старых данных делать не нужно).
5. `just deploy <окружение>`: архив WAL и таймеры включаются, первый полный бэкап новой линии времени — сразу.

Объекты Garage (артефакты проверок, FST) не восстанавливаются: пакеты задач деплой импортирует снова, ссылки старых отправок на артефакты ведут в пустоту.

## Место на диске

```sh
df -h / && docker system df
docker builder prune --keep-storage 10GB -f   # кэш сборки образов
```

Логи контейнеров ограничены (5 × 20 МБ на контейнер), журнал — 1 ГБ.

## Доступ к хосту

SSH пускает только по ключам. Если доступ потерян (ключ, файрвол), войдите через консоль VPS в панели AEZA. Остановка файрвола — `systemctl stop nftables` (удаляет только таблицу `inet apparatica`, правила Docker остаются).
