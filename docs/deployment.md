# Развёртывание

Как платформа ставится на серверы: что на них работает, как их подготовить и как выкатить коммит. Серверы описаны кодом в `deploy/ansible`, сервисы — тот же `deploy/compose.yaml`, что у [стенда](stand.md), с `deploy/compose.server.yaml` сверху. Операции на работающем сервере (откат, логи, сертификаты, сбои) — в [`deploy/RUNBOOK.md`](../deploy/RUNBOOK.md). Каждый коммит `master` после зелёного CI выкатывается на staging сам ([деплой из CI](#деплой-из-ci)).

## Окружения и хосты

| Окружение | Хосты | Имена |
|---|---|---|
| `staging` | один VPS `apparatica.app` (AEZA, 4 vCPU, 8 ГБ, Debian 13): роли `app` и `worker`; бэкапы — Cloudflare R2, бакет `apparatica-staging-backups` в юрисдикции EU | `staging.apparatica.app` — сайт и API, `s3.staging.apparatica.app` — S3 для presigned URL, `waveview.staging.apparatica.app` — просмотрщик волн |

Инвентарь — `deploy/ansible/inventories/<окружение>/`: `hosts.yml` (хосты и группы) и `group_vars/all.yml` (имена, размер Garage, мониторинг, бэкапы). Корневой домен `apparatica.app` оставлен для production (T3.14).

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
| `base` | все | пакеты; SSH только по ключам (`PasswordAuthentication no`, `PermitRootLogin prohibit-password`); пользователь `deploy` с ключами `base_deploy_keys` из инвентаря и sudo без пароля ([деплой из CI](#деплой-из-ci)); файрвол; ежедневные обновления Debian (`unattended-upgrades` с источниками Debian по умолчанию, без перезагрузок); журнал не больше 1 ГБ |
| `gvisor` | `worker` | `runsc` версии `gvisor_version` из apt-репозитория gVisor; платформа `systrap` по умолчанию (на VPS нет вложенной виртуализации) |
| `docker` | все | Docker Engine версии `docker_version` с плагинами compose и buildx; `daemon.json`: драйвер cgroup `systemd`, логи контейнеров `json-file` до 5 файлов по 20 МБ, рантайм `runsc` у хостов `worker` |
| `apparatica` | `app` | релиз, настройки, секреты, сервисы, проверки (ниже), таймеры бэкапов ([backups.md](backups.md#на-сервере)) |

**Файрвол** — своя таблица nftables `inet apparatica`: входящие на хост только `22`, `80`, `443` и `443/udp` (HTTP/3), ICMP и ответы на свои соединения. Таблицы Docker не трогаются: в `/etc/nftables.conf` нет `flush ruleset`, а остановка сервиса `nftables` удаляет только нашу таблицу. Порты контейнеров проходят хук `forward`, а не `input`, поэтому снаружи доступно только то, что публикует compose. На сервере публикует порты только Caddy, Grafana слушает `127.0.0.1:3000`.

**Версии Docker и gVisor** заданы в `roles/*/defaults/main.yml`. `unattended-upgrades` их не обновляет: их репозиториев нет среди источников обновлений. Новая версия ставится сменой значения и `just provision --tags host`. Docker при смене конфигурации перезапускается вместе со всеми контейнерами.

## На сервере

| Путь | Что там |
|---|---|
| `/opt/apparatica/releases/<релиз>/` | файлы репозитория коммита релиза, кроме `brief/`; `release.env` — образы `api`, `web`, `worker` релиза (пуст, если они собраны на хосте) |
| `/opt/apparatica/current` | ссылка на запущенный релиз |
| `/etc/apparatica/settings.env` | настройки compose из инвентаря: имена, `APX_ENVIRONMENT=production`, `APX_COOKIE_SECURE=true`, `SANDBOX_RUNTIME=runsc`, `GARAGE_CAPACITY_GB`, `POSTGRES_ARCHIVE_MODE` и хранилище бэкапов `BACKUP_S3_*` |
| `/etc/apparatica/secrets.env` | секреты (ниже), права `0600` |
| `/usr/local/sbin/apparatica-secrets` | генератор секретов |
| `/etc/systemd/system/apparatica-backup*.{service,timer}` | полный бэкап и проверка восстановления ([backups.md](backups.md#на-сервере)), если бэкапы включены |

Сервисы — проект compose `apparatica` из `deploy/compose.yaml` и `deploy/compose.server.yaml`:

```sh
cd /opt/apparatica/current
docker compose -f deploy/compose.yaml -f deploy/compose.server.yaml \
  --env-file /etc/apparatica/settings.env --env-file /etc/apparatica/secrets.env ps
```

`compose.server.yaml` меняет у стенда только то, что зависит от сервера:

- Caddy слушает `80` и `443` с `deploy/Caddyfile.server`: публичные имена, сертификаты Let's Encrypt (Caddy получает и продлевает их сам, хранит в томе `caddy-data`), HSTS на год, HTTP отвечает редиректом. Остальные заголовки и CSP — как на стенде ([security.md](security.md#csp-сайта)). Garage находит бакет `waveview` по заголовку `Host`, поэтому Caddy передаёт ему `Host: waveview`.
- Адреса браузера у API (`APX_S3_PUBLIC_URL`, `APX_WAVEVIEW_URL`), у `web` (CSP и `PUBLIC_BASE_URL` для OG-картинок) и CORS бакета артефактов — `https://` публичных имён.
- Grafana без анонимного доступа и только на `127.0.0.1:3000`.
- `garage-setup` не получает ключа `backup`: бэкапы базы уходят в хранилище другого провайдера ([backups.md](backups.md)), а не в Garage того же хоста.
- Проверки `storage-check` и `judge-check` идут через Caddy по HTTPS под публичными именами, но имена в их контейнерах ведут на сам хост (`host-gateway`). Так проверяется развёртывание, а не кэши публичных резолверов; к тому же у сети контейнеров нет IPv6, и запись AAAA без A давала бы `Network is unreachable`.

Тест `scripts/test_server_deploy.py` следит, чтобы ни один адрес стенда (`localhost`) не остался без замены, а каждый секрет compose со значением по умолчанию генерировался.

## Секреты

У каждого секрета `deploy/compose.yaml` есть публичное значение по умолчанию для стенда. На сервере все они берутся из `/etc/apparatica/secrets.env`. Файл создаёт `apparatica-secrets` при первом деплое: случайные hex-строки, ключи Garage вида `GK` + 24 hex. Повторный запуск дописывает только недостающие, поэтому секрет, появившийся в новом релизе, генерируется при его первом деплое. В репозиторий и на машину оператора секреты не попадают.

Ключ шифрования бэкапов `BACKUP_ENCRYPTION_KEY` генерируется так же, но менять его нельзя: старые бэкапы станут нечитаемыми.

Ключи, которые выдаёт провайдер, не генерируются: ключ хранилища бэкапов (`BACKUP_S3_KEY_ID`, `BACKUP_S3_KEY_SECRET`, [backups.md](backups.md#на-сервере)), токен бота алертов (`TELEGRAM_BOT_TOKEN`, [alerts.md](alerts.md#бот-и-чат)), ключи OAuth-приложений (`APX_GITHUB_CLIENT_ID`, `APX_GITHUB_CLIENT_SECRET`) и адрес почтового relay с ключом (`APX_SMTP_URL`, [ниже](#почта)). Без них сервер работает без входа через провайдера и без входа по почте; чтобы включить вход, допишите их в `secrets.env` и повторите деплой. Callback URL приложения GitHub — `https://<SITE_HOST>/api/v1/auth/github/callback` ([configuration.md](configuration.md#переменные-окружения)).

### Почта

Письма со ссылкой входа уходят через SMTP-relay Brevo (Франция, данные в ЕС; обработчик в [legal.md](legal.md#обработчики-ст-28)). Хостинг закрывает исходящие порты 25, 465 и 587, поэтому relay — на порту 2525 со STARTTLS:

```
APX_SMTP_URL=smtp+starttls://<логин SMTP>:<ключ SMTP>@smtp-relay.brevo.com:2525
```

Логин и ключ — в Brevo: SMTP & API → SMTP; `@` логина записывается как `%40`. Отправитель — `apparatica_mail_from` инвентаря (`MAIL_FROM` в `settings.env`, у staging `Apparatica <noreply@apparatica.app>`): его домен подтверждается в Brevo (Senders, Domains & Dedicated IPs → Domains) записями DNS, которые Brevo выдаёт, — код Brevo, DKIM, SPF (`include:spf.brevo.com`) и DMARC. Без них письма уходят в спам или отклоняются. Доставку видно по метрике `apparatica_mail_letters_total` ([configuration.md](configuration.md#метрики)).

**Сохраните копию `secrets.env` вне сервера** (менеджер паролей): без `BACKUP_ENCRYPTION_KEY` из неё бэкапы не расшифровать, без остальных ключей восстановленные данные не прочитать ключами нового сервера, а гости потеряют свои отправки. Смена секрета — в [RUNBOOK](../deploy/RUNBOOK.md#смена-секрета).

## Деплой

`just deploy staging` (`deploy.yml`, роль `apparatica`):

1. **Релиз.** На машине оператора `git archive` коммита `HEAD` упаковывает файлы репозитория без `brief/`. Если есть незакоммиченные изменения отслеживаемых или добавленных в индекс файлов, они входят в релиз (`git stash create`), а имя релиза получает суффикс: `<коммит>-dirty-<stash>`. Неотслеживаемые файлы не входят. Архив распаковывается в `/opt/apparatica/releases/<релиз>/`.
2. **Настройки и секреты** — `/etc/apparatica` (выше).
3. **Образы.** Образ Postgres с WAL-G (`deploy/postgres`) всегда собирается на хосте и называется по git-дереву этого каталога: `POSTGRES_IMAGE=apparatica-postgres:<хэш>` в `release.env`. Уже собранный не пересобирается, и пока `deploy/postgres` не меняется, контейнер Postgres не пересоздаётся. С `-e apparatica_image_tag=sha-<коммит>` (так деплоит CI) релиз берёт опубликованные образы `ghcr.io/apparatica/{api,web,worker}:sha-<коммит>`: они записываются в `release.env` релиза, скачиваются, если их ещё нет на хосте, и ничего не собирается (`up --no-build`: нет образа — нет деплоя). Тег должен быть тегом коммита релиза, а дерево — чистым, иначе деплой останавливается до изменений на хосте. Без тега (`just deploy` оператора) образы собираются на хосте из файлов релиза. Образы тулчейна и просмотрщика всегда скачиваются из GHCR.
4. **Сервисы.** `up -d --wait` для `caddy valkey-queue valkey-cache ingest worker`, как `just up`. Миграции (`migrate`) и настройка Garage (`garage-setup`) выполняются до запуска API. Затем импортируются задачи релиза (`demo-problems`), а с `apparatica_monitoring` запускаются Prometheus, Alertmanager, node-exporter и Grafana.
5. **Ссылка `current`** переключается на релиз.
6. **Проверки** (`apparatica_checks`): `storage-check` (ключи, presigned URL, CORS, сайт `waveview` и его заголовки) и `judge-check` (эталон и мутант `mux4` проверяются через `https://<сайт>` под gVisor) — то же, что `just stand-check`, кроме бэкапа: его проверяет еженедельный таймер. Упавшая проверка роняет деплой, но новый релиз уже запущен; вернуть прежний — `just rollback`.
7. **Уборка.** Остаются последние `apparatica_keep_releases` (5) релизов, текущий — всегда. Опубликованные образы и образы Postgres, которых нет в `release.env` оставшихся релизов, и висячие образы сборок удаляются.
8. **Бэкапы.** С `apparatica_backups: true` ставятся таймеры бэкапов, а если в хранилище ещё нет полного бэкапа или записи о нём для алертов, он делается сразу; с `false` таймеры удаляются ([backups.md](backups.md#на-сервере)).

Первый деплой на чистом хосте длится около 15 минут: сборка образов и скачивание тулчейна. Следующие идут быстрее за счёт кэша сборки Docker.

## Деплой из CI

Workflow `.github/workflows/staging.yml` запускается после зелёного CI на push в `master` (`workflow_run`) и вручную из `master` (`workflow_dispatch`). Деплои идут по одному, по порядку: новый коммит ждёт текущего деплоя.

| Job | Что делает |
|---|---|
| Images | собирает `api` (`backend/Dockerfile`), `worker`, `web` из коммита и публикует `ghcr.io/apparatica/<имя>:sha-<12 знаков коммита>`; метка `org.opencontainers.image.source` связывает пакет с репозиторием |
| Deploy | environment `staging`: `just deploy staging -e ansible_user=deploy -e apparatica_image_tag=sha-<коммит>` с ключом `STAGING_SSH_KEY`; хост проверяется по `deploy/ansible/inventories/staging/known_hosts` |
| End-to-end tests | `just e2e` против `https://staging.apparatica.app` в Chrome раннера, без входа по ссылке из письма (`E2E_MAILPIT_URL` пуст: письма staging не попадают в Mailpit); при падении — артефакт `e2e-staging-report` |

**Пользователь `deploy`.** CI заходит не как `root`, а как `deploy` со своим ключом и выполняет те же плейбуки через sudo. По силе это root, и ограничивать его нет смысла: коммит `master` и так исполняется на хосте (у `sandboxd` docker socket). Свой пользователь отделяет ключ CI от ключей операторов: его можно отозвать, удалив из `base_deploy_keys`, и вход CI виден в журнале как `deploy`. Секрет доступен только job'ам environment `staging`, а environment принимает только ветку `master`. Pull request'ы и форки его не получают.

**Настройка GitHub** (один раз, делает мейнтейнер):

1. Settings → Environments → `staging`: Deployment branches and tags — Selected branches, `master`.
2. Секрет environment `STAGING_SSH_KEY` — приватный ключ, чей публичный указан в `base_deploy_keys` (`ssh-keygen -t ed25519 -C apparatica-ci-staging`). Новый ключ попадает на хост через `just provision staging --tags host`.
3. После первой публикации: пакеты `api`, `web`, `worker` организации — Package settings → Change visibility → Public, как у `toolchain` и `waveview`. Пакеты, созданные из Actions, приватны, и хост не скачает их без входа в GHCR. Затем перезапустите workflow.

## Мониторинг

Prometheus, Alertmanager, node-exporter и Grafana из профиля `monitoring` ([stand.md](stand.md#мониторинг)) работают на хосте приложения (`apparatica_monitoring: true`). Порты не публикуются, кроме Grafana на loopback. node-exporter видит корень хоста только для чтения и читает метрики бэкапов из `/var/lib/apparatica/metrics`. Алерты уходят в Telegram, если заданы `apparatica_alert_telegram_chat_id` и `TELEGRAM_BOT_TOKEN` ([alerts.md](alerts.md)).

Grafana не опубликована, её открывают через SSH-туннель:

```sh
ssh -L 3000:127.0.0.1:3000 root@apparatica.app   # затем http://localhost:3000
```

Вход — `admin` и `GRAFANA_ADMIN_PASSWORD` из `/etc/apparatica/secrets.env`.

## Лицензия библиотеки синтеза

Образ тулчейна содержит liberty Nangate45 (FreePDK45 Open Cell Library), её `LICENSE` и `README.md` лежат рядом, в `/opt/pdk/nangate45/` ([toolchain/README.md](../toolchain/README.md#nangate45)). Это единственная зависимость, лицензия которой не входит в список открытых лицензий проекта (ADR-0007, NFR-MAINT-07): по уведомлению Nangate она запрещает сравнивать библиотеку с другими и не предназначена для коммерческого использования. Какая лицензия действует на самом деле — открытый вопрос ОВ-21. Проект бесплатный и некоммерческий; **коммерческий форк или инстанс должен оценить лицензию сам** или заменить библиотеку.
