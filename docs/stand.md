# Стенд

Вся платформа на одной машине в docker compose: сервисы, хранилище с бакетами и ключами, воркер с песочницей, демо-задачи (NFR-MAINT-06). Файлы — в `deploy/`.

## Запуск

Нужны Docker с Compose v2 и `just`; на Windows — Docker Desktop.

```sh
just up            # собрать образы, мигрировать БД, настроить Garage, зарегистрировать профиль
                   # тулчейна, запустить воркер, импортировать задачи
just stand-check   # проверить хранилище (права ключей, presigned URL, CORS, сайт waveview),
                   # проверку решений гостя через весь стенд, бэкап базы и восстановление из него
just backup-check  # только бэкап базы и проверка восстановления (docs/backups.md)
just monitoring    # Prometheus, Alertmanager, node-exporter и Grafana рядом с запущенным стендом
just logs api web  # логи сервисов
just down          # остановить (и мониторинг); данные в томах остаются (удалить: docker compose … down -v)
```

Без `just` то же делает `docker compose -f deploy/compose.yaml up -d --build`. Сайт — http://localhost:8080.

`just up` подключает ещё `deploy/compose.dev.yaml`: он публикует сервисы данных на `127.0.0.1`, чтобы бэкенд, фронтенд и тесты можно было запускать на хосте рядом со стендом. Порты — в таблице ниже.

## Адреса

| Адрес | Что там |
|---|---|
| http://localhost:8080 | сайт; `/api/*` — API (документация — `/api/v1/docs`) |
| http://s3.localhost:8080 | S3 API хранилища: по нему браузер скачивает артефакты по presigned URL |
| http://waveview.web.localhost:8080 | бакет `waveview` как сайт: просмотрщик волн на своём origin, `/<версия>/index.html` ([waveview.md](waveview.md)) |
| http://grafana.localhost:8080 | Grafana с дашбордом очередей, только после `just monitoring` ([«Мониторинг»](#мониторинг)) |
| `127.0.0.1:5432` | Postgres (`apparatica` / `apparatica`), только с `compose.dev.yaml` |
| `127.0.0.1:6379`, `6380` | `valkey-queue`, `valkey-cache`, только с `compose.dev.yaml` |
| `127.0.0.1:3900` | S3 API Garage напрямую, только с `compose.dev.yaml` |
| http://localhost:8025 | Mailpit: письма стенда, например со ссылкой входа; SMTP для API на хосте — `127.0.0.1:1025`. Только с `compose.dev.yaml` |

Браузеры и большинство систем разрешают `*.localhost` в `127.0.0.1` сами. Если нет, добавьте имена в `hosts`.

## Сервисы

| Сервис | Что делает |
|---|---|
| `caddy` | proxy: `localhost` — сайт и API (`/api` без буферизации, для SSE), `s3.localhost` и `waveview.web.localhost` — Garage, `grafana.localhost` — Grafana; заголовки безопасности, у `waveview` — свои (CSP с `frame-ancestors` сайта, CORS, ответ на `OPTIONS`). Только HTTP: TLS — со staging (T1.23b). CSP страниц ставит сам `web` ([security.md](security.md#csp-сайта)) |
| `api` | FastAPI (`backend/Dockerfile`) |
| `ingest` | `apparatica ingest` из того же образа: результаты проверок в Postgres, `finalized`, watchdog, сроки хранения артефактов, процент принятых. С ключом хранилища `ingest` и пользователем Valkey `ingest` |
| `web` | Next.js, standalone-сервер (`web/Dockerfile`); серверный рендер читает `api` напрямую (`API_URL=http://api:8000`) и стартует после него; `S3_PUBLIC_URL` и `WAVEVIEW_URL` — origin хранилища и просмотрщика для CSP страниц |
| `postgres` | PostgreSQL 17 с WAL-G (`deploy/postgres`, образ собирается из `POSTGRES_BASE_IMAGE`, по умолчанию `postgres:17-trixie`), локаль `builtin C.UTF-8` (регистр символов — средствами PostgreSQL, поиск по кириллице не зависит от ОС образа). Архивирует WAL в бакет `backups` Garage ([backups.md](backups.md)) |
| `valkey-queue` | очереди и стримы: AOF, без вытеснения. Пользователи и их ключи — `deploy/valkey/queue-users.acl.in` ([security.md](security.md#права-компонентов)); пароли — `VALKEY_QUEUE_API_PASSWORD`, `VALKEY_QUEUE_WORKER_PASSWORD`, `VALKEY_QUEUE_INGEST_PASSWORD`. API ставит в него проверки как `api`, воркер берёт их как `worker`, ингестор читает результаты как `ingest` |
| `valkey-cache` | кэш и rate limit: без сохранения на диск, LRU. API хранит в нём счётчики rate limit и квоты волн ([api.md](api.md#авторы-и-лимиты)) |
| `garage` | S3-хранилище (ADR-0013), один узел |
| `waveview` | одноразовый: копирует сайт просмотрщика из образа `WAVEVIEW_IMAGE` (по умолчанию `ghcr.io/apparatica/waveview:<версия>`) в том для `garage-setup`; локальная сборка — `WAVEVIEW_IMAGE=apparatica-waveview:dev` ([waveview.md](waveview.md)) |
| `garage-setup` | одноразовый: раскладка узла, бакеты, ключи компонентов и их права, сайт `waveview` и загрузка в него новых версий просмотрщика, CORS, правила жизненного цикла (`deploy/garage/setup.py`) |
| `migrate` | одноразовый: `apparatica migrate` |
| `demo-problems` | одноразовый: `apparatica-admin problems import --publish` для `problems/` |
| `toolchain` | одноразовый: образ тулчейна песочниц по digest (`TOOLCHAIN_IMAGE@TOOLCHAIN_DIGEST`); compose скачивает его до первой проверки, а сервис копирует из него `versions.lock` в том для `toolchain-profile` |
| `toolchain-profile` | одноразовый: регистрирует образ профилем тулчейна по умолчанию (`deploy/worker/toolchain-profile.sh`) |
| `sandboxd` | `apx-sandboxd` из образа воркера (`worker/Dockerfile`), см. [«Воркер и песочница»](#воркер-и-песочница) |
| `worker` | `apparatica-worker`: проверки из очередей в песочницах `sandboxd`. С ключом хранилища `worker` и пользователем Valkey `worker`, без Postgres и Docker |
| `mailpit` | только с `compose.dev.yaml`: SMTP-сервер, который никуда не отправляет письма, а показывает их (`MAILPIT_IMAGE`, по умолчанию `axllent/mailpit:v1.33.0`); `api` шлёт в него письма (`APX_SMTP_URL=smtp://mailpit:1025`), ссылки в них ведут на `APX_PUBLIC_BASE_URL` — `http://localhost:8080` |
| `prometheus`, `alertmanager`, `node-exporter`, `grafana` | мониторинг и алерты, запускаются только `just monitoring` (профиль `monitoring`), см. [«Мониторинг»](#мониторинг) |
| `storage-check`, `judge-check`, `backup-check` | проверки стенда, запускаются только `just stand-check` (профиль `check`): хранилище (`deploy/garage/check.py`), проверка решений (`deploy/worker/check.py`) и восстановление последнего бэкапа базы (`apx-backup check`, [backups.md](backups.md)) |

Одноразовые сервисы идемпотентны и выполняются при каждом `up`: повторный импорт пропускает неизменённые версии, настройка Garage ничего не пересоздаёт.

## Воркер и песочница

Проверки идут так же, как в production (ADR-0003, [architecture.md](architecture.md#оркестратор)): `worker` берёт задание из `valkey-queue`, а контейнеры песочницы создаёт через `apx-sandboxd`. Демон — сервис `sandboxd`:

- он единственный получает docker socket хоста (`/var/run/docker.sock`), поэтому работает от root и фактически root на хосте; сети у него нет;
- песочницы — соседние контейнеры того же Docker с меткой `apparatica.sandbox`, а не вложенные. `docker compose down` их не удаляет: оставшиеся после остановки демон убирает при следующем старте;
- unix-сокет демона лежит в томе `sandboxd-socket`, общем с `worker`, с группой пользователя воркера;
- разрешён только репозиторий `TOOLCHAIN_IMAGE`.

**Рантайм** — `SANDBOX_RUNTIME`, одно значение для демона и воркера. По умолчанию `runc`: так стенд работает и на Docker Desktop, где gVisor нет. `runsc` — если он зарегистрирован в Docker хоста, как в CI. Изоляцию `runc` не обеспечивает: стенд с `runc` не для чужого кода.

**Профиль тулчейна.** Стенд берёт опубликованный образ `ghcr.io/apparatica/toolchain` по digest из `compose.yaml` и регистрирует его профилем `sv-<TOOLCHAIN_PROFILE>` по умолчанию; версии инструментов профиля читаются из `versions.lock` самого образа. Новый профиль на стенд приходит сменой digest в `compose.yaml`, когда образ опубликован. Локальная сборка (`just toolchain-build`) подключается так:

```sh
docker image inspect apparatica-toolchain:dev --format '{{index .RepoDigests 0}}'   # apparatica-toolchain@sha256:…
# deploy/.env
TOOLCHAIN_IMAGE=apparatica-toolchain
TOOLCHAIN_DIGEST=sha256:…
TOOLCHAIN_PROFILE_ID=sv-dev-1   # профиль неизменяем: у другого образа — другой id
```

Профиль с тем же id, но другим образом `toolchain-profile` не перезапишет и завершится ошибкой: задайте новый `TOOLCHAIN_PROFILE_ID`.

## Мониторинг

`just monitoring` поднимает рядом с запущенным стендом Prometheus, Alertmanager, node-exporter и Grafana (профиль `monitoring`; `just up` их не запускает). Prometheus (`deploy/prometheus/prometheus.yml`) раз в 15 с опрашивает `api:8000/metrics`, `ingest:9100`, `worker:9100` ([configuration.md](configuration.md#метрики)) и `node-exporter:9100` (на стенде — метрики, которые видит его контейнер) и хранит данные 7 дней в томе `prometheus`. Снаружи их не видно.

Grafana открывается на http://grafana.localhost:8080: смотреть можно без входа, менять — под `admin` с паролем `GRAFANA_ADMIN_PASSWORD` (по умолчанию `apparatica`). Источник данных и дашборды подключаются из `deploy/grafana/provisioning`. Дашборд «Apparatica: очереди и проверки» (`deploy/grafana/dashboards/apparatica.json`) открывается по умолчанию и меняется только в репозитории: в интерфейсе он только для чтения. На нём:
- очереди: сколько проверок ждёт, сколько ждёт самая старая, p50/p95 ожидания, записи `judge:results` без записи в базу;
- загрузка слотов воркеров по пулам;
- p50/p95 времени этапов и доля `internal_error` по этапам, итоги проверок;
- запросы и ошибки API, p95 времени ответа по роутам, задержка стрима и открытые стримы, записи ингестора.

Правила алертов (`deploy/prometheus/rules`) загружаются и на стенде, но бэкапы тут не пишут метрик для них, а Alertmanager без `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` ничего не отправляет: алерты видно в Grafana → Alerting ([alerts.md](alerts.md#доставка)). Проверка правил и конфигураций без стенда — `just alerts-test`.

## Хранилище

`garage-setup` создаёт бакеты `packages`, `artifacts`, `build-cache`, `waveview` и импортирует ключи `api`, `worker`, `ingest` с правами по ADR-0013, а для бэкапов базы — бакет `backups` и ключ `backup` с правами только на него ([backups.md](backups.md#на-стенде)). CORS бакета `artifacts` разрешает GET и HEAD с сайта: страница задачи сама скачивает FST и передаёт байты просмотрщику, iframe `waveview` в хранилище не ходит. Правила жизненного цикла:
- незавершённые multipart-загрузки удаляются через сутки во всех бакетах;
- `build-cache` очищается через сутки.

Сроки хранения остальных артефактов соблюдает ингестор по `artifacts.expires_at` ([architecture.md](architecture.md#ingest)), поэтому у ключа `ingest` есть право `write` на `artifacts`: в Garage удаление объекта входит в него.

Что проверено и какие у Garage особенности — в ADR-0013 («Проверка в T0.19»).

## Настройки и секреты

Значения по умолчанию заданы в `compose.yaml`, поэтому чистый checkout запускается без настройки. Секреты по умолчанию (пароль БД, ключ токенов заданий, ключ cookie гостя, соль адресов, секреты и ключи Garage, ключ шифрования бэкапов) публичны. Стенд, к которому есть доступ у других, должен задать свои значения в `deploy/.env`. Список переменных — `deploy/.env.example`, файл `deploy/.env` в git не попадает.

Там же задаются:
- порт сайта (`HTTP_PORT`);
- `APX_COOKIE_SECURE`: на стенде по HTTP cookie гостя без `Secure` (по умолчанию `false`), за HTTPS — `true`;
- порты `compose.dev.yaml` — если, например, 5432 уже занят Postgres на хосте;
- рантайм песочниц (`SANDBOX_RUNTIME`) и образ тулчейна (`TOOLCHAIN_IMAGE`, `TOOLCHAIN_DIGEST`, `TOOLCHAIN_PROFILE_ID`), см. [«Воркер и песочница»](#воркер-и-песочница);
- пароль администратора Grafana (`GRAFANA_ADMIN_PASSWORD`);
- образы. Если Docker Hub недоступен, их можно брать через зеркало (`VALKEY_IMAGE=mirror.gcr.io/valkey/valkey:8-alpine` …; базовые образы сборки — `POSTGRES_BASE_IMAGE`, `PYTHON_IMAGE`, `NODE_IMAGE`, `DOCKER_CLI_IMAGE`; мониторинг — `PROMETHEUS_IMAGE`, `ALERTMANAGER_IMAGE`, `NODE_EXPORTER_IMAGE`, `GRAFANA_IMAGE`; `just alerts-test` читает `PROMETHEUS_IMAGE` и `ALERTMANAGER_IMAGE` из окружения, не из `deploy/.env`).

## e2e-тесты

`e2e/` — Playwright и axe против запущенного стенда с настоящим воркером (specs/09 §4.4):

```sh
just up
just e2e                                          # E2E_BASE_URL=http://localhost:8080, E2E_BROWSER=chrome, E2E_MAILPIT_URL=http://localhost:8025
E2E_BROWSER=msedge just e2e                       # Windows: Edge
E2E_BASE_URL=http://localhost:18080 just e2e -g guest   # другой порт, фильтр по имени теста
```

Браузер — установленный Chrome или Edge (канал Playwright), отдельные браузеры Playwright не скачиваются. Тесты идут по одному: у стенда один воркер.

| Тест | Что проверяет |
|---|---|
| `guest-solves.spec.ts` | гость решает `mux4`: Run с ошибкой (мутант `m01`) падает на открытом тесте, «Показать на диаграмме» открывает FST в просмотрщике (панель волн в состоянии `normal`), Submit эталона — «Принято»; код вставляется в Monaco как из буфера, и тест сверяет его с телом `POST /submissions`; страница с вердиктом проходит axe |
| `email-login.spec.ts` | гость входит по ссылке из письма: «Войти» в шапке задачи ведёт на `/login?next=/problems/mux4`, адрес (новый на каждый прогон, `e2e-…@example.com`) уходит в форму, письмо «Вход в Apparatica» читается из API Mailpit (`E2E_MAILPIT_URL`), ссылка из него возвращает на задачу вошедшим (кнопка меню с ником `user-…`, без баннера гостя), почта видна в настройках, повторное открытие ссылки — «Ссылка не подходит», «Выйти» снова делает браузер гостем; страница входа и страница негодной ссылки проходят axe. Без Mailpit (пустой `E2E_MAILPIT_URL`, так на staging) тест пропускается. Импорт гостевых решений из сценария 2 specs/09 §4.4 появится с ним самим (Ф4, T4.5) |
| `accessibility.spec.ts` | axe на каталоге и странице задачи в светлой и тёмной темах, на широком экране и на телефоне (Pixel 7: без редактора, с блоком «Решать удобнее на компьютере») |
| `security-headers.spec.ts` | CSP страницы: свой nonce у каждого ответа и у всех скриптов страницы, без `unsafe-eval`; страницы 404 с политикой; заголовки Caddy ([security.md](security.md#csp-сайта)) |

Каждый тест падает, если браузер сообщил в консоли страницы или её фреймов о нарушении Content Security Policy (`tests/fixtures.ts`). axe (`tests/axe.ts`) проверяет правила WCAG 2.2 A и AA и не допускает нарушений уровня serious и critical (NFR-A11Y-06). Frame `waveview` в проверку не входит: у него непрозрачный origin. При падении Playwright сохраняет трассу в `e2e/test-results/` (`pnpm -C e2e exec playwright show-trace <файл>`).

## CI

Job `Stand` в `ci.yml` ставит на `ubuntu-24.04` gVisor, поднимает стенд с нуля с `SANDBOX_RUNTIME=runsc` (`just up`), запускает `just stand-check` — с ним и эталон и мутант демо-задачи через весь стенд, и бэкап базы с восстановлением — проверяет через Caddy здоровье API, каталог и страницу и запускает `just e2e` с Chrome раннера; при падении отчёт Playwright и трассы — артефакт `e2e-report`. Лимит job'а — 20 минут: по NFR-MAINT-06 стенд должен подниматься на чистой машине за 15.
