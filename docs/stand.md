# Стенд

Вся платформа на одной машине в docker compose: сервисы, хранилище с бакетами и ключами, демо-задачи (NFR-MAINT-06). Файлы — в `deploy/`.

## Запуск

Нужны Docker с Compose v2 и `just`; на Windows — Docker Desktop.

```sh
just up            # собрать образы, мигрировать БД, настроить Garage, импортировать задачи
just stand-check   # проверить хранилище: права ключей, presigned URL, CORS, сайт waveview
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
| `valkey-queue` | очереди и стримы: AOF, без вытеснения. Пользователи и их ключи — `deploy/valkey/queue-users.acl.in` ([security.md](security.md#права-компонентов)); пароли — `VALKEY_QUEUE_API_PASSWORD`, `VALKEY_QUEUE_WORKER_PASSWORD`, `VALKEY_QUEUE_INGEST_PASSWORD`. API ставит в него проверки как `api`, ингестор читает результаты как `ingest`; воркера на стенде пока нет (T1.21), поэтому отправки остаются в очереди |
| `valkey-cache` | кэш и rate limit: без сохранения на диск, LRU. API хранит в нём счётчики rate limit и квоты волн ([api.md](api.md#гости-и-лимиты-ф1)) |
| `garage` | S3-хранилище (ADR-0013), один узел |
| `waveview` | одноразовый: копирует сайт просмотрщика из образа `WAVEVIEW_IMAGE` (по умолчанию `ghcr.io/apparatica/waveview:<версия>`) в том для `garage-setup`; локальная сборка — `WAVEVIEW_IMAGE=apparatica-waveview:dev` ([waveview.md](waveview.md)) |
| `garage-setup` | одноразовый: раскладка узла, бакеты, ключи компонентов и их права, сайт `waveview` и загрузка в него новых версий просмотрщика, CORS, правила жизненного цикла (`deploy/garage/setup.py`) |
| `migrate` | одноразовый: `apparatica migrate` |
| `demo-problems` | одноразовый: `apparatica-admin problems import --publish` для `problems/` |
| `storage-check` | проверка хранилища, запускается только `just stand-check` (профиль `check`) |

Одноразовые сервисы идемпотентны и выполняются при каждом `up`: повторный импорт пропускает неизменённые версии, настройка Garage ничего не пересоздаёт.

Профиля тулчейна и воркера на стенде пока нет, поэтому `POST /api/v1/submissions` отвечает `503 JUDGE_UNAVAILABLE`. Воркер появится в Ф1.

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
- образы. Если Docker Hub недоступен, их можно брать через зеркало (`POSTGRES_IMAGE=mirror.gcr.io/library/postgres:17-alpine` …; базовые образы сборки — `PYTHON_IMAGE`, `NODE_IMAGE`).

## CI

Job `Stand` в `ci.yml` поднимает стенд с нуля на `ubuntu-24.04` (`just up`), запускает `just stand-check` и проверяет через Caddy здоровье API, каталог и страницу. Лимит job'а — 20 минут: по NFR-MAINT-06 стенд должен подниматься на чистой машине за 15.
