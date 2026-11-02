# RUNBOOK

Операции на работающем сервере. Как устроено развёртывание — [docs/deployment.md](../docs/deployment.md). Команды `just` запускаются из корня репозитория на машине оператора, остальные — на сервере под `root`. Ниже `dc` — compose платформы:

```sh
cd /opt/apparatica/current
alias dc='docker compose -f deploy/compose.yaml -f deploy/compose.server.yaml --env-file /etc/apparatica/settings.env --env-file /etc/apparatica/secrets.env'
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

## Место на диске

```sh
df -h / && docker system df
docker builder prune --keep-storage 10GB -f   # кэш сборки образов
```

Логи контейнеров ограничены (5 × 20 МБ на контейнер), журнал — 1 ГБ.

## Доступ к хосту

SSH пускает только по ключам. Если доступ потерян (ключ, файрвол), войдите через консоль VPS в панели AEZA. Остановка файрвола — `systemctl stop nftables` (удаляет только таблицу `inet apparatica`, правила Docker остаются).
