# Стенд

Вся платформа на одной машине в docker compose: сервисы, хранилище с бакетами и ключами, воркер с песочницей, демо-задачи (NFR-MAINT-06). Файлы — в `deploy/`.

## Запуск

Нужны Docker с Compose v2 и `just`; на Windows — Docker Desktop.

```sh
just up            # собрать образы, мигрировать БД, настроить Garage, зарегистрировать профиль
                   # тулчейна, запустить воркер, импортировать задачи
just stand-check   # проверить хранилище (права ключей, presigned URL, CORS, сайт waveview)
                   # и проверку решений гостя через весь стенд
just logs api web  # логи сервисов
just down          # остановить; данные в томах остаются (удалить: docker compose … down -v)
```

Без `just` то же делает `docker compose -f deploy/compose.yaml up -d --build`. Сайт — http://localhost:8080.

`just up` подключает ещё `deploy/compose.dev.yaml`: он публикует сервисы данных на `127.0.0.1`, чтобы бэкенд, фронтенд и тесты можно было запускать на хосте рядом со стендом. Порты — в таблице ниже.

## Адреса

| Адрес | Что там |
|---|---|
| http://localhost:8080 | сайт; `/api/*` — API (документация — `/api/v1/docs`) |
| http://s3.localhost:8080 | S3 API хранилища: по нему браузер скачивает артефакты по presigned URL |
| http://waveview.web.localhost:8080 | бакет `waveview` как сайт: просмотрщик волн на своём origin, `/<версия>/index.html` ([waveview.md](waveview.md)) |
| `127.0.0.1:5432` | Postgres (`apparatica` / `apparatica`), только с `compose.dev.yaml` |
| `127.0.0.1:6379`, `6380` | `valkey-queue`, `valkey-cache`, только с `compose.dev.yaml` |
| `127.0.0.1:3900` | S3 API Garage напрямую, только с `compose.dev.yaml` |

Браузеры и большинство систем разрешают `*.localhost` в `127.0.0.1` сами. Если нет, добавьте имена в `hosts`.

## Сервисы

| Сервис | Что делает |
|---|---|
| `caddy` | proxy: `localhost` — сайт и API (`/api` без буферизации, для SSE), `s3.localhost` и `waveview.web.localhost` — Garage; заголовки безопасности, у `waveview` — свои (CSP с `frame-ancestors` сайта, CORS, ответ на `OPTIONS`). Только HTTP: TLS — со staging (T1.23) |
| `api` | FastAPI (`backend/Dockerfile`) |
| `ingest` | `apparatica ingest` из того же образа: результаты проверок в Postgres, `finalized`, watchdog, сроки хранения артефактов, процент принятых. С ключом хранилища `ingest` и пользователем Valkey `ingest` |
| `web` | Next.js, standalone-сервер (`web/Dockerfile`); серверный рендер читает `api` напрямую (`API_URL=http://api:8000`) и стартует после него |
| `postgres` | PostgreSQL 17, локаль `builtin C.UTF-8` (регистр символов — средствами PostgreSQL, поиск по кириллице не зависит от ОС образа) |
| `valkey-queue` | очереди и стримы: AOF, без вытеснения. Пользователи и их ключи — `deploy/valkey/queue-users.acl.in` ([security.md](security.md#права-компонентов)); пароли — `VALKEY_QUEUE_API_PASSWORD`, `VALKEY_QUEUE_WORKER_PASSWORD`, `VALKEY_QUEUE_INGEST_PASSWORD`. API ставит в него проверки как `api`, воркер берёт их как `worker`, ингестор читает результаты как `ingest` |
| `valkey-cache` | кэш и rate limit: без сохранения на диск, LRU. API хранит в нём счётчики rate limit и квоты волн ([api.md](api.md#гости-и-лимиты-ф1)) |
| `garage` | S3-хранилище (ADR-0013), один узел |
| `waveview` | одноразовый: копирует сайт просмотрщика из образа `WAVEVIEW_IMAGE` (по умолчанию `ghcr.io/apparatica/waveview:<версия>`) в том для `garage-setup`; локальная сборка — `WAVEVIEW_IMAGE=apparatica-waveview:dev` ([waveview.md](waveview.md)) |
| `garage-setup` | одноразовый: раскладка узла, бакеты, ключи компонентов и их права, сайт `waveview` и загрузка в него новых версий просмотрщика, CORS, правила жизненного цикла (`deploy/garage/setup.py`) |
| `migrate` | одноразовый: `apparatica migrate` |
| `demo-problems` | одноразовый: `apparatica-admin problems import --publish` для `problems/` |
| `toolchain` | одноразовый: образ тулчейна песочниц по digest (`TOOLCHAIN_IMAGE@TOOLCHAIN_DIGEST`); compose скачивает его до первой проверки, а сервис копирует из него `versions.lock` в том для `toolchain-profile` |
| `toolchain-profile` | одноразовый: регистрирует образ профилем тулчейна по умолчанию (`deploy/worker/toolchain-profile.sh`) |
| `sandboxd` | `apx-sandboxd` из образа воркера (`worker/Dockerfile`), см. [«Воркер и песочница»](#воркер-и-песочница) |
| `worker` | `apparatica-worker`: проверки из очередей в песочницах `sandboxd`. С ключом хранилища `worker` и пользователем Valkey `worker`, без Postgres и Docker |
| `storage-check`, `judge-check` | проверки стенда, запускаются только `just stand-check` (профиль `check`): хранилище (`deploy/garage/check.py`) и проверка решений (`deploy/worker/check.py`) |

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

## Хранилище

`garage-setup` создаёт бакеты `packages`, `artifacts`, `build-cache`, `waveview` и импортирует ключи `api`, `worker`, `ingest` с правами по ADR-0013. CORS бакета `artifacts` разрешает GET и HEAD с сайта: страница задачи сама скачивает FST и передаёт байты просмотрщику, iframe `waveview` в хранилище не ходит. Правила жизненного цикла:
- незавершённые multipart-загрузки удаляются через сутки во всех бакетах;
- `build-cache` очищается через сутки.

Сроки хранения остальных артефактов соблюдает ингестор по `artifacts.expires_at` ([architecture.md](architecture.md#ingest)), поэтому у ключа `ingest` есть право `write` на `artifacts`: в Garage удаление объекта входит в него.

Что проверено и какие у Garage особенности — в ADR-0013 («Проверка в T0.19»).

## Настройки и секреты

Значения по умолчанию заданы в `compose.yaml`, поэтому чистый checkout запускается без настройки. Секреты по умолчанию (пароль БД, ключ токенов заданий, ключ cookie гостя, соль адресов, секреты и ключи Garage) публичны. Стенд, к которому есть доступ у других, должен задать свои значения в `deploy/.env`. Список переменных — `deploy/.env.example`, файл `deploy/.env` в git не попадает.

Там же задаются:
- порт сайта (`HTTP_PORT`);
- `APX_COOKIE_SECURE`: на стенде по HTTP cookie гостя без `Secure` (по умолчанию `false`), за HTTPS — `true`;
- порты `compose.dev.yaml` — если, например, 5432 уже занят Postgres на хосте;
- рантайм песочниц (`SANDBOX_RUNTIME`) и образ тулчейна (`TOOLCHAIN_IMAGE`, `TOOLCHAIN_DIGEST`, `TOOLCHAIN_PROFILE_ID`), см. [«Воркер и песочница»](#воркер-и-песочница);
- образы. Если Docker Hub недоступен, их можно брать через зеркало (`POSTGRES_IMAGE=mirror.gcr.io/library/postgres:17-alpine` …; базовые образы сборки — `PYTHON_IMAGE`, `NODE_IMAGE`, `DOCKER_CLI_IMAGE`).

## e2e-тесты

`e2e/` — Playwright и axe против запущенного стенда с настоящим воркером (specs/09 §4.4):

```sh
just up
just e2e                                          # E2E_BASE_URL=http://localhost:8080, E2E_BROWSER=chrome
E2E_BROWSER=msedge just e2e                       # Windows: Edge
E2E_BASE_URL=http://localhost:18080 just e2e -g guest   # другой порт, фильтр по имени теста
```

Браузер — установленный Chrome или Edge (канал Playwright), отдельные браузеры Playwright не скачиваются. Тесты идут по одному: у стенда один воркер.

| Тест | Что проверяет |
|---|---|
| `guest-solves.spec.ts` | гость решает `mux4`: Run с ошибкой (мутант `m01`) падает на открытом тесте, «Показать на диаграмме» открывает FST в просмотрщике (панель волн в состоянии `normal`), Submit эталона — «Принято»; код вставляется в Monaco как из буфера, и тест сверяет его с телом `POST /submissions`; страница с вердиктом проходит axe |
| `accessibility.spec.ts` | axe на каталоге и странице задачи в светлой и тёмной темах |

axe (`tests/axe.ts`) проверяет правила WCAG 2.2 A и AA и не допускает нарушений уровня serious и critical (NFR-A11Y-06). Frame `waveview` в проверку не входит: у него непрозрачный origin. При падении Playwright сохраняет трассу в `e2e/test-results/` (`pnpm -C e2e exec playwright show-trace <файл>`).

## CI

Job `Stand` в `ci.yml` ставит на `ubuntu-24.04` gVisor, поднимает стенд с нуля с `SANDBOX_RUNTIME=runsc` (`just up`), запускает `just stand-check` — с ним и эталон и мутант демо-задачи через весь стенд — проверяет через Caddy здоровье API, каталог и страницу и запускает `just e2e` с Chrome раннера; при падении отчёт Playwright и трассы — артефакт `e2e-report`. Лимит job'а — 20 минут: по NFR-MAINT-06 стенд должен подниматься на чистой машине за 15.
