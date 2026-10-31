# Развёртывание

Как платформа ставится на серверы: что на них работает, как их подготовить и как выкатить коммит. Серверы описаны кодом в `deploy/ansible`, сервисы — тот же `deploy/compose.yaml`, что у [стенда](stand.md), с `deploy/compose.server.yaml` сверху. Операции на работающем сервере (откат, логи, сертификаты, сбои) — в [`deploy/RUNBOOK.md`](../deploy/RUNBOOK.md).

## Окружения и хосты

| Окружение | Хосты | Имена |
|---|---|---|
| `staging` | один VPS `apparatica.app` (AEZA, 4 vCPU, 8 ГБ, Debian 13): роли `app` и `worker` | `staging.apparatica.app` — сайт и API, `s3.staging.apparatica.app` — S3 для presigned URL, `waveview.staging.apparatica.app` — просмотрщик волн |

Инвентарь — `deploy/ansible/inventories/<окружение>/`: `hosts.yml` (хосты и группы) и `group_vars/all.yml` (имена, размер Garage, мониторинг). Корневой домен `apparatica.app` оставлен для production (T3.14).

**Роли хостов.** Группа `app` — хосты платформы, `worker` — хосты песочниц. gVisor ставится только хостам `worker`, и только у них Docker получает рантайм `runsc`. Пока хост один, он входит в обе группы: роль `apparatica` поднимает все сервисы compose вместе и отказывается работать на хосте `app` без `worker`. Отдельному хосту воркера нужна частная сеть до `valkey-queue` и Garage хоста приложения, она появится вместе со вторым VPS.

**DNS.** Записи A и AAAA всех трёх имён указывают на хост `app` (у staging — `138.124.52.47` и `2a0b:4140:b31::2`; адрес IPv6 — тот, что на интерфейсе хоста, `ip -6 addr`, а не `::1` его сети). Let's Encrypt проверяет имя сначала по IPv6, так что неверная AAAA срывает выдачу сертификата. Без записей Caddy не получит сертификаты. Публичные резолверы, которых спросили до появления записи, помнят её отсутствие до 30 минут: первый деплой лучше запускать, когда запись видна у нескольких (`dig @8.8.8.8`, `dig @1.1.1.1`).

## Что нужно на своей машине

- Docker: Ansible работает в контейнере (`deploy/ansible/Dockerfile`, версии — `deploy/ansible/poetry.lock`), поэтому плейбуки одинаково запускаются в Linux, macOS и Windows.
- SSH-доступ к хостам под `root` по ключу из `~/.ssh` и запись хоста в `~/.ssh/known_hosts`. Каталог `~/.ssh` монтируется в контейнер только для чтения, а ключи копируются в контейнер с правами, которых требует ssh.
- `just`.

```sh
just provision staging                # подготовить хосты и выкатить текущий коммит
just provision staging --tags host    # только хосты: пакеты, файрвол, Docker, gVisor
just deploy staging                   # выкатить текущий коммит
just rollback <релиз> staging         # снова запустить сохранённый релиз (RUNBOOK)
just lint-ansible                     # ansible-lint и проверка синтаксиса плейбуков
```

Аргументы после окружения уходят в `ansible-playbook` (`--check --diff` — посмотреть изменения, ничего не меняя). Без доступа к Docker Hub базовый образ контейнера берётся из зеркала: `PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim just deploy`.

## Подготовка хоста

`site.yml` — роли по порядку; повторный запуск ничего не меняет.

| Роль | Хосты | Что делает |
|---|---|---|
| `base` | все | пакеты; SSH только по ключам (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`); файрвол; ежедневные обновления Debian (`unattended-upgrades` с источниками Debian по умолчанию, без перезагрузок); журнал не больше 1 ГБ |
| `gvisor` | `worker` | `runsc` версии `gvisor_version` из apt-репозитория gVisor; платформа `systrap` по умолчанию (на VPS нет вложенной виртуализации) |
| `docker` | все | Docker Engine версии `docker_version` с плагинами compose и buildx; `daemon.json`: драйвер cgroup `systemd`, логи контейнеров `json-file` до 5 файлов по 20 МБ, рантайм `runsc` у хостов `worker` |
| `apparatica` | `app` | релиз, настройки, секреты, сервисы, проверки (ниже) |

**Файрвол** — своя таблица nftables `inet apparatica`: входящие на хост только `22`, `80`, `443` и `443/udp` (HTTP/3), ICMP и ответы на свои соединения. Таблицы Docker не трогаются: в `/etc/nftables.conf` нет `flush ruleset`, а остановка сервиса `nftables` удаляет только нашу таблицу. Порты контейнеров проходят хук `forward`, а не `input`, поэтому снаружи доступно только то, что публикует compose. На сервере публикует порты только Caddy, Grafana слушает `127.0.0.1:3000`.

**Версии Docker и gVisor** заданы в `roles/*/defaults/main.yml`. `unattended-upgrades` их не обновляет: их репозиториев нет среди источников обновлений. Новая версия ставится сменой значения и `just provision --tags host`. Docker при смене конфигурации перезапускается вместе со всеми контейнерами.

## На сервере

| Путь | Что там |
|---|---|
| `/opt/apparatica/releases/<релиз>/` | файлы репозитория коммита релиза, кроме `brief/` |
| `/opt/apparatica/current` | ссылка на запущенный релиз |
| `/etc/apparatica/settings.env` | настройки compose из инвентаря: имена, `APX_ENVIRONMENT=production`, `APX_COOKIE_SECURE=true`, `SANDBOX_RUNTIME=runsc`, `GARAGE_CAPACITY_GB` |
| `/etc/apparatica/secrets.env` | секреты (ниже), права `0600` |
| `/usr/local/sbin/apparatica-secrets` | генератор секретов |

Сервисы — проект compose `apparatica` из `deploy/compose.yaml` и `deploy/compose.server.yaml`:

```sh
cd /opt/apparatica/current
docker compose -f deploy/compose.yaml -f deploy/compose.server.yaml \
  --env-file /etc/apparatica/settings.env --env-file /etc/apparatica/secrets.env ps
```

`compose.server.yaml` меняет у стенда только то, что зависит от сервера:

- Caddy слушает `80` и `443` с `deploy/Caddyfile.server`: публичные имена, сертификаты Let's Encrypt (Caddy получает и продлевает их сам, хранит в томе `caddy-data`), HSTS на год, HTTP отвечает редиректом. Остальные заголовки и CSP — как на стенде ([security.md](security.md#csp-сайта)). Garage находит бакет `waveview` по заголовку `Host`, поэтому Caddy передаёт ему `Host: waveview`.
- Адреса браузера у API (`APX_S3_PUBLIC_URL`, `APX_WAVEVIEW_URL`), у `web` (CSP) и CORS бакета артефактов — `https://` публичных имён.
- Grafana без анонимного доступа и только на `127.0.0.1:3000`.
- Проверки `storage-check` и `judge-check` идут через Caddy по HTTPS под публичными именами, но имена в их контейнерах ведут на сам хост (`host-gateway`). Так проверяется развёртывание, а не кэши публичных резолверов; к тому же у сети контейнеров нет IPv6, и запись AAAA без A давала бы `Network is unreachable`.

Тест `scripts/test_server_deploy.py` следит, чтобы ни один адрес стенда (`localhost`) не остался без замены, а каждый секрет compose генерировался.

## Секреты

У каждого секрета `deploy/compose.yaml` есть публичное значение по умолчанию для стенда. На сервере все они берутся из `/etc/apparatica/secrets.env`. Файл создаёт `apparatica-secrets` при первом деплое: случайные hex-строки, ключи Garage вида `GK` + 24 hex. Повторный запуск дописывает только недостающие, поэтому секрет, появившийся в новом релизе, генерируется при его первом деплое. В репозиторий и на машину оператора секреты не попадают.

**Сохраните копию `secrets.env` вне сервера** (менеджер паролей): без неё восстановленные из бэкапа данные не прочитать ключами нового сервера, а гости потеряют свои отправки. Смена секрета — в [RUNBOOK](../deploy/RUNBOOK.md#смена-секрета).

## Деплой

`just deploy staging` (`deploy.yml`, роль `apparatica`):

1. **Релиз.** На машине оператора `git archive` коммита `HEAD` упаковывает файлы репозитория без `brief/`. Если есть незакоммиченные изменения отслеживаемых или добавленных в индекс файлов, они входят в релиз (`git stash create`), а имя релиза получает суффикс: `<коммит>-dirty-<stash>`. Неотслеживаемые файлы не входят. Архив распаковывается в `/opt/apparatica/releases/<релиз>/`.
2. **Настройки и секреты** — `/etc/apparatica` (выше).
3. **Сервисы.** `up -d --build --wait` для `caddy valkey-queue valkey-cache ingest worker`, как `just up`: образы `api`, `web` и `worker` собираются на хосте из файлов релиза, образы тулчейна и просмотрщика скачиваются из GHCR. Миграции (`migrate`) и настройка Garage (`garage-setup`) выполняются до запуска API. Затем импортируются задачи релиза (`demo-problems`), а с `apparatica_monitoring` запускаются Prometheus и Grafana.
4. **Ссылка `current`** переключается на релиз.
5. **Проверки** (`apparatica_checks`): `storage-check` (ключи, presigned URL, CORS, сайт `waveview` и его заголовки) и `judge-check` (эталон и мутант `mux4` проверяются через `https://<сайт>` под gVisor) — то же, что `just stand-check`. Упавшая проверка роняет деплой, но новый релиз уже запущен; вернуть прежний — `just rollback`.
6. **Уборка.** Остаются последние `apparatica_keep_releases` (5) релизов, текущий — всегда. Образы, которые не использует ни один контейнер, удаляются (`docker image prune`).

Первый деплой на чистом хосте длится около 15 минут: сборка образов и скачивание тулчейна. Следующие идут быстрее за счёт кэша сборки Docker.

## Мониторинг

Prometheus и Grafana из профиля `monitoring` ([stand.md](stand.md#мониторинг)) работают на хосте приложения. Grafana не опубликована, её открывают через SSH-туннель:

```sh
ssh -L 3000:127.0.0.1:3000 root@apparatica.app   # затем http://localhost:3000
```

Вход — `admin` и `GRAFANA_ADMIN_PASSWORD` из `/etc/apparatica/secrets.env`.
