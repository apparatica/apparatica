# Разработка

Как поставить окружение, запускать проверки и где что лежит. Правила веток, коммитов и PR — в [CONTRIBUTING.md](../CONTRIBUTING.md).

## Что нужно установить

| Инструмент | Версия | Зачем |
|---|---|---|
| Python | 3.13 | `judge`, `backend`, `worker` (ADR-0001); другие версии проекты не принимают |
| Poetry | ≥ 2.2 | зависимости Python; нужна поддержка `[dependency-groups]` |
| Node.js | ≥ 22 | фронтенд и JS-инструменты |
| pnpm | 11 (версия закреплена в `packageManager` корневого `package.json`) | зависимости JS |
| just | любая актуальная | точка входа для команд (`justfile`) |
| pre-commit | ≥ 4 | git-хуки |
| Docker | ≥ 24 | образ тулчейна (`toolchain-build`, `toolchain-test`) |

Пример установки на Windows: `winget install Casey.Just`, `pipx install pre-commit`; на macOS — `brew install just pre-commit`; на Linux — пакетный менеджер дистрибутива или `pipx install pre-commit` и `cargo install just`.

Стенд (`just up`) появится в T0.19.

## Первый запуск

```sh
just install   # poetry install в judge, backend, worker; pnpm install; pre-commit install
just check     # всё, что проверяет CI
```

Poetry создаёт виртуальное окружение внутри каждого проекта (`judge/.venv`, `backend/.venv`, `worker/.venv`, настройка в `poetry.toml`). Если Poetry выбрал не тот интерпретатор, укажите его явно: `poetry -C judge env use <путь к python3.13>` и повторите `just install`.

## Команды

| Команда | Что делает |
|---|---|
| `just` | список команд |
| `just install` | ставит зависимости Python и JS (`install-py`, `install-js`), подключает git-хуки |
| `just lint` | `lint-py` (ruff: линт и проверка форматирования), `lint-imports` (архитектурные контракты), `lint-js` (eslint и prettier `--check` в `web/`) |
| `just fmt` | применяет ruff format, безопасные исправления ruff и prettier в `web/` |
| `just typecheck` | `typecheck-py` (mypy `--strict` в каждом Python-проекте, для `scripts/` и Python-кода `toolchain/` с `--platform linux`) и `typecheck-js` (`tsc` в `web/`) |
| `just test` | `test-py` (pytest в каждом Python-проекте и тесты `scripts/`) и `test-js` (Vitest в `web/`) |
| `just build-js` | production-сборка фронтенда (`next build`) |
| `just storybook`, `just build-storybook` | Storybook доменных компонентов: http://localhost:6006 и статическая сборка в `web/storybook-static` ([frontend.md](frontend.md#доменные-компоненты)) |
| `just check-locks` | `poetry check --lock` в каждом проекте и сверка версий общих зависимостей между тремя `poetry.lock` |
| `just check-licenses` | лицензии зависимостей Python (`check-licenses-py`) и JS (`check-licenses-js`) по политике |
| `just check` | `check-locks`, `check-licenses`, `check-api`, `lint`, `typecheck`, `test` |
| `just openapi` | пересоздаёт контракт API: `backend/openapi.json` из кода и типы TS-клиента ([api.md](api.md)) |
| `just check-api` | проверяет, что типы TS-клиента совпадают с `backend/openapi.json` |
| `just dev-mocks` | фронтенд на моках API, без бэкенда: http://localhost:3000 ([frontend.md](frontend.md#моки-для-разработки)) |
| `just record-scenarios` | записывает сценарии проверок для моков реальными прогонами в образе тулчейна (нужен Docker) |
| `just mock-problems` | пересоздаёт демо-задачи моков (`web/src/mocks/problem-versions.json`) из пакетов `problems/` ([frontend.md](frontend.md#моки-для-разработки)) |
| `just up`, `just down`, `just logs` | стенд в docker compose: все сервисы и демо-задачи на http://localhost:8080 ([stand.md](stand.md)) |
| `just stand-check` | проверка хранилища запущенного стенда |
| `just validate-problems` | `judge validate` всех пакетов `problems/` в образе тулчейна (нужен Docker) |
| `just schemas` | перегенерирует JSON Schema из моделей судьи: `problem.yaml` и записи протокола тестбенча (`judge/schemas/`) |
| `just toolchain-build` | собирает образ тулчейна `apparatica-toolchain:dev` |
| `just toolchain-test` | тесты образа: pytest на хосте, команды через `docker exec` в контейнере с ограничениями песочницы |

Рецепты `justfile` работают и в sh (Linux, macOS, CI), и в PowerShell 7 (Windows).

## CI

GitHub Actions, `.github/workflows/ci.yml`, на GitHub-hosted раннерах `ubuntu-24.04`. Запускается на push в `master`, на каждый pull request и вручную. Три параллельных job'а вызывают те же рецепты `just`, что и локальная проверка:

| Job | Шаги |
|---|---|
| Python | `install-py`, `check-locks`, `lint-py`, `lint-imports`, `typecheck-py`, `test-py`, `check-licenses-py` |
| JS | `install-js`, `lint-js`, `typecheck-js`, `check-api`, `test-js`, `build-js`, `build-storybook`, `check-licenses-js` |
| Stand | `up`, `stand-check` и проверка сайта и API через Caddy ([stand.md](stand.md#ci)) |

Образ тулчейна собирает и публикует отдельный workflow `.github/workflows/toolchain.yml` — при изменениях в `toolchain/` и в коде судьи, чьи тесты против образа он прогоняет; публикует только при изменении входов образа (подробности — [toolchain/README.md](../toolchain/README.md)).

Задачи проверяет workflow `.github/workflows/problems.yml`: `judge validate --determinism` в образе тулчейна, собранном из той же ревизии (кэш слоёв общий с `toolchain.yml`). Какие пакеты проверять, решает `scripts/changed_problems.py`: на pull request и push — изменённые пакеты `problems/<id>/`; если изменились судья (`judge/src`, `judge/poetry.lock`), образ (`toolchain/`), классы ресурсов или сам workflow — все пакеты (регрессия эталонов, мутантов и детерминизма). Раз в неделю и вручную (`workflow_dispatch`) проверяются все пакеты. Локально то же самое — `just validate-problems`. Чтобы PR с невалидным пакетом нельзя было слить, job `Validate packages` нужно сделать обязательной проверкой в настройках защиты ветки `master`.

Python 3.13 и Poetry (версия в `POETRY_VERSION` workflow) ставятся в job'е, виртуальные окружения кэшируются по хэшу `poetry.lock`; Node 24 и pnpm — из `packageManager`, кэш pnpm-store. Сторонние actions закреплены по SHA коммита, версия — в комментарии. Unit-тесты TS добавятся в JS job вместе с Vitest (T0.20).

## Архитектурные контракты

import-linter проверяет границу ядра и языковых модулей (ADR-0011, NFR-MAINT-04). Контракты лежат в `[tool.importlinter]` проекта, чьё окружение их проверяет:

| Проект | Контракт |
|---|---|
| `judge` | `judge.core` не импортирует `judge.languages` |
| `backend` | `apparatica` не импортирует `judge.languages` ни напрямую, ни через другие модули `judge` |
| `backend` | `apparatica.core` не импортирует остальные модули бэкенда (specs/03 §3) |
| `backend` | модули зависят друг от друга в одну сторону: `admin → submissions → problems → core` |

Языковые модули подключаются к ядру через entry points реестра (`judge.core.registry`), поэтому исключений в контрактах нет. Новые границы (например, между модулями бэкенда) добавляются в те же секции.

## Лицензии зависимостей

`scripts/check_licenses.py` сверяет лицензии всех установленных Python-пакетов (из метаданных окружения каждого проекта) и JS-пакетов (`pnpm licenses list --json -r`) с политикой `scripts/license-policy.toml` (NFR-MAINT-07, ADR-0012):

- `allowed` — SPDX-идентификаторы, совместимые с AGPL-3.0-or-later. Выражения `OR`, `AND`, `WITH` разбираются: для `OR` достаточно одной разрешённой лицензии, для `AND` нужны все;
- `aliases` — нестандартные (не SPDX) названия из метаданных и классификаторов PyPI (`MIT License` → `MIT`);
- `exceptions` — явно допущенные зависимости с несовместимой лицензией; каждое исключение ссылается на ADR. Сейчас единственное — liberty Nangate45 (ADR-0007), она проверяется с образом тулчейна.

Если проверка упала на новой зависимости: при пермиссивной или совместимой лицензии, которой нет в списке, расширьте `allowed` и список в ADR-0012 в том же PR; при нестандартном названии — добавьте алиас; если лицензия несовместима — замените зависимость. Исключение требует ADR.

## Структура репозитория

```
judge/      пакет судьи и CLI (Poetry, пакет judge); judge/schemas/ — сгенерированные JSON Schema; ядро — docs/judge.md
backend/    FastAPI-приложение и ингестор (Poetry, пакет apparatica)
worker/     воркер и оркестратор песочницы (Poetry, пакет apparatica_worker)
web/        фронтенд: Next.js-приложение (frontend.md)
.github/    CI (GitHub Actions)
toolchain/  образ тулчейна песочницы: Dockerfile, versions.lock, apx-run, apx-verilate, apx_tb_pkg, тесты образа
config/     конфигурация: классы ресурсов судьи, уровни сложности, лимиты (configuration.md)
deploy/     стенд в docker compose: compose.yaml, compose.dev.yaml, Caddyfile, настройка Garage (stand.md)
problems/   пакеты задач, CC BY-SA 4.0
scripts/    служебные скрипты: сверка lock-файлов и лицензий, политика лицензий
docs/       проектная документация
specs/      спецификация и план
brief/      исходные материалы заказчика (не редактируются)
```

Остальные каталоги из [specs/03 §6](../specs/03-architecture.md) (`tests/`) появляются вместе с задачами, которые их наполняют.

## Python-проекты

У `judge`, `backend` и `worker` свои `pyproject.toml` (PEP 621) и `poetry.lock`. `backend` и `worker` подключают `judge` как path-зависимость с `develop = true`: правка судьи сразу видна в них без переустановки.

Зависимость добавляется в конкретный проект: `poetry -C backend add <пакет>` (для инструментов разработки — `--group dev`). Если пакет есть и в других проектах, версии должны совпадать — иначе упадёт `just check-locks`; выровняйте ограничения и выполните `poetry -C <проект> lock`.

Настройки инструментов:
- ruff — общий `ruff.toml` в корне (Python 3.13, длина строки 100); Markdown и `brief/` исключены; кириллица разрешена в `allowed-confusables` (сообщения и тексты по-русски), длинные строки — в таблицах случаев тестов `precheck`;
- mypy — `[tool.mypy]` в `pyproject.toml` каждого проекта, `strict = true`;
- pytest — `[tool.pytest.ini_options]` там же.

## Бэкенд: `apparatica`

FastAPI-приложение (`backend/src/apparatica`, модульный монолит по specs/03 §3). Модули появляются вместе со своими задачами плана:

- `core` — настройки, БД (SQLAlchemy async), ошибки `problem+json`, request id, логи, feature flags (таблица `feature_flags`) и эндпоинты `GET /api/v1/health` и `GET /api/v1/config`;
- `problems` — таблицы `tags`, `problems`, `problem_versions`, `reference_solutions`; импорт пакетов задач; API каталога (`GET /api/v1/problems`, `/problems/{slug}`, `/problems/{slug}/versions/{version}`, `/tags`);
- `submissions` — таблицы `toolchain_profiles`, `submissions`, `stage_results`, `artifacts`; API отправок (`POST /api/v1/submissions`, `GET /submissions/{id}`), токены заданий, профили тулчейна;
- `admin` — CLI `apparatica-admin`.

Контракт API (`backend/openapi.json`, TS-клиент) и правила его изменения — [api.md](api.md).

Модули зависят друг от друга в одну сторону: `admin → submissions → problems → core`. Это контракт import-linter (`[tool.importlinter]` в `backend/pyproject.toml`).

```sh
poetry -C backend run apparatica serve --reload   # http://127.0.0.1:8000/api/v1/docs
poetry -C backend run apparatica migrate          # alembic upgrade head
poetry -C backend run apparatica openapi          # документ OpenAPI в stdout (just openapi)
```

Нужен Postgres 17+ по `APX_DATABASE_URL` (например, со стенда: `just up` публикует его на `127.0.0.1:5432`, [stand.md](stand.md)); без него API стартует, но `GET /health` отвечает 503. Настройки и файлы `config/` — [configuration.md](configuration.md).

### API каталога задач

- **Видимость.** В каталоге — опубликованные задачи с их текущими версиями. `GET /problems/{slug}/versions/{version}` отдаёт версии до текущей включительно: на старые ссылаются отправки. Версия новее текущей (импортирована без `--publish`) и неопубликованная задача — `404 NOT_FOUND`.
- **Фильтры `GET /problems`.** Несколько значений `difficulty` или `tag` — «любое из», фильтры разных видов складываются. `q` ищет подстроку без учёта регистра в названии, слаге и подписи тега. `sort`: `number`, `difficulty` (порядок `config/difficulties.yaml`, затем номер), `acceptance` (процент принятых); с `-` — по убыванию. Задачи без процента принятых идут последними в обе стороны, при равенстве — по номеру. Страницы — `page`, `per_page` (по умолчанию `per_page` из `config/catalog.yaml` — 12, максимум 100). Фильтра по статусу в API нет: статусы гостя живут в браузере ([frontend.md](frontend.md#каталог)), статусы вошедших появятся в Ф2.
- **Процент принятых** (`acceptance`, FR-CAT-04) есть в строках каталога и в `GET /problems/{slug}`; в `GET /problems/{slug}/versions/{version}` его нет, потому что данные версии неизменяемы и кэшируются на год (схема `ProblemVersionDetail`, у текущей версии — `ProblemDetail`). Это доля авторов с принятым Submit среди авторов хотя бы одного Submit с вердиктом, от 0 до 1; `null`, пока таких Submit нет. Считаются все версии задачи. Submit без вердикта (`queued`, `running`, `cancelled`, `internal_error`) и Run не учитываются; автор в Ф1 — гость (`guest_id`). Числа хранит таблица `problem_stats`, её раз в `APX_PROBLEM_STATS_EVERY_S` (5 минут) пересчитывает ингестор ([architecture.md](architecture.md#ingest)). Гостевые отправки удаляются через 14 дней (ОВ-13), поэтому гости входят в процент, пока их отправки хранятся.
- **Сводка `progress`.** Число опубликованных задач каждого уровня, без учёта фильтров. Решённые гостем сайт считает по локальной истории браузера, решённые вошедшим появятся в Ф2.
- **Кэш.** Каталог, задача и теги — `public, max-age=60, stale-while-revalidate=300` с `ETag`. Версия задачи неизменяема — `public, max-age=31536000, immutable`.

### База данных и миграции

Схема — модели SQLAlchemy в `models.py` модулей. `apparatica.models` импортирует их все, и по нему Alembic видит полную схему. Схема соответствует specs/04 §4. Таблицы следующих фаз создаются их миграциями, заранее их не заводят.

- **Ключи.** Первичные ключи — UUIDv7. Их выдаёт приложение (`default` модели) при flush; если id нужен раньше, задайте его явно (`id=uuid7()`).
- **Имена ограничений.** Задаются соглашением в `apparatica.core.db` (`pk_`, `fk_`, `uq_`, `ix_`, `ck_`).
- **Статусы.** Типы `submission_status` и `stage_status` — перечисления Postgres. Их значения берутся из ядра судьи (`judge.core.verdict`, `judge.core.stage`). Новый статус в судье требует миграции (`ALTER TYPE … ADD VALUE`); тест сверяет значения в БД с кодом.

Миграции лежат в пакете (`apparatica/migrations/versions`). Новая ревизия создаётся из каталога `backend` (там `alembic.ini`):

```sh
APX_DATABASE_URL=… poetry run alembic revision --autogenerate --rev-id 0002 -m "..."
```

Autogenerate нужна база на текущей ревизии. Результат проверяется вручную, потому что Alembic сам не:
- выносит в отдельный `create_foreign_key` взаимные ссылки таблиц (`problems.current_version_id`);
- удаляет перечисления в `downgrade`.

`poetry run alembic check` показывает, совпадает ли схема базы с моделями.

### Импорт задач

```sh
poetry -C backend run apparatica-admin problems import ../problems             # новые версии
poetry -C backend run apparatica-admin problems import --publish ../problems   # и сделать их текущими
```

Аргументы — пакеты или каталоги с пакетами, как у `judge validate`. Нужны Postgres и S3 (`APX_S3_*`, [configuration.md](configuration.md)).

Что делает импорт (`apparatica.problems.importer`, specs/06 §6):
1. **Проверяет пакеты.** Читает `problem.yaml` по модели судьи и считает `content_hash`. Тесты не прогоняются: это уже сделал `judge validate` в CI. Ещё проверяет, что `difficulty` есть в `config/difficulties.yaml`, а теги — в `tags.yaml`. Файл тегов ищется рядом с пакетами, другой путь задаётся через `--tags`.
2. **Синхронизирует теги.** Записывает теги из файла, порядок в файле становится сортировкой. Теги, которых нет в файле, остаются: на них могут ссылаться старые версии.
3. **Сравнивает каждый пакет с базой:**
   - новая `(slug, version)` — пакет упаковывается и загружается в бакет `packages` под ключом `<slug>/<version>-<content_hash>.tar.zst`, создаются версия и её эталоны;
   - та же версия с тем же хэшем — ничего не меняется;
   - та же версия с другим хэшем — отказ: опубликованная версия неизменяема;
   - отказ также, если версия старше уже импортированной или `number` занят другой задачей либо отличается от номера задачи в базе.
4. **Публикует (с `--publish`).** Делает версию текущей и задачу опубликованной. Версию старше текущей опубликовать нельзя.

Импорт атомарен: при любом отказе база не меняется. Он печатает все найденные отказы и завершается с кодом 1. Пакет загружается в хранилище до коммита, поэтому у версии в базе пакет всегда есть. Если коммит не прошёл, в бакете может остаться лишний объект; повторный импорт перезапишет его тем же содержимым.

### Профили тулчейна

Отправка проверяется профилем тулчейна по умолчанию для языка задачи (specs/09 §2). Профиль регистрируется по опубликованному образу:

```sh
poetry -C backend run apparatica-admin toolchain add sv-2026.10.2 \
  --image ghcr.io/<owner>/apparatica-toolchain --digest sha256:<digest> \
  --versions ../toolchain/versions.lock --normalization-version 1 --default
```

- **Версии инструментов** берутся из ключей `*_VERSION` файла `versions.lock` того образа (`{"verilator": "5.052", …}`).
- **`--normalization-version`** — версия нормализации AST-хэша судьи (`n<версия>:` в метриках `precheck`).
- **Неизменяемость.** Профиль неизменяем, как тег образа. Повторный `add` с теми же данными ничего не меняет, с другими — отказ.
- **По умолчанию.** `--default` делает профиль профилем по умолчанию для языка; у прежнего профиля по умолчанию флаг снимается. Повторный `add` с `--default` переключает профиль.

### Тесты

Тесты бэкенда (`backend/tests`) поднимают приложение через `TestClient`. Где нужна только связь с БД, вместо Postgres используется SQLite в памяти (`aiosqlite`).

Тесты схемы, миграций, импорта и API (`test_db.py`, `test_cli.py`, `test_problem_import.py`, `test_problems_api.py`, `test_submissions_api.py`, `test_job_tokens_and_profiles.py`) работают с настоящим Postgres; S3 в тестах импорта эмулирует moto. Как устроен Postgres в тестах:

- **Сервер.** Fixture `postgres` поднимает его через testcontainers один раз на сессию. Нужен Docker. Без Docker тесты пропускаются, а в CI (переменная `CI`) падают.
- **Изоляция.** Миграции применяются один раз к базе-шаблону. Каждый тест получает свою копию (`CREATE DATABASE … TEMPLATE`). Для тестов API есть второй шаблон, `catalogue_template`, — с опубликованными задачами из `problems/`.
- **Образ.** По умолчанию `postgres:17-alpine`. Если Docker Hub недоступен, образ задаётся через `APX_TEST_POSTGRES_IMAGE`, например `mirror.gcr.io/library/postgres:17-alpine`.

Тесты очереди (`backend/tests/test_queue.py`, `worker/tests/test_worker.py`) работают с настоящим Valkey: fixture поднимает его через testcontainers один раз на сессию, правила те же, что у Postgres. Образ по умолчанию — `valkey/valkey:8-alpine`, переопределяется через `APX_TEST_VALKEY_IMAGE` (например, `mirror.gcr.io/valkey/valkey:8-alpine`).

### Воркер

Воркер работает на Linux-хосте с Docker, рядом с `apx-sandboxd` (тот слушает unix-сокет, на Windows не запускается):

```sh
APX_SANDBOXD_RUNTIME=runc APX_SANDBOXD_SOCKET=/tmp/sandboxd.sock poetry -C worker run apx-sandboxd
APX_QUEUE_URL=redis://worker:<пароль>@localhost:6379/0 APX_SANDBOXD_SOCKET=/tmp/sandboxd.sock \
  APX_SANDBOX_RUNTIME=runc APX_RESOURCE_CLASSES=../config/resource-classes.yaml \
  APX_PACKAGE_CACHE=/tmp/apx-packages APX_S3_ENDPOINT_URL=http://localhost:3900 \
  APX_S3_ACCESS_KEY_ID=<ключ воркера> APX_S3_SECRET_ACCESS_KEY=<секрет> \
  poetry -C worker run apparatica-worker
```

Он берёт проверки из очередей `valkey-queue` (на стенде с `compose.dev.yaml` — `localhost:6379`, пользователь `worker`, пароль `VALKEY_QUEUE_WORKER_PASSWORD`) до Ctrl+C или SIGTERM; начатые проверки при остановке доводятся до конца. Настройки — [configuration.md](configuration.md#воркер).

### Ингестор

```sh
APX_QUEUE_URL=redis://ingest:<пароль>@localhost:6379/0 APX_JOB_TOKEN_KEY=<ключ API> \
  APX_CONFIG_DIR=../config poetry -C backend run apparatica ingest
```

Переносит результаты проверок из `judge:results` в Postgres до Ctrl+C или SIGTERM, а если он лидер — запускает watchdog и удаление истёкших артефактов (тогда нужны и `APX_S3_*` с ключом `ingest`) ([architecture.md](architecture.md#ingest)). Ключ токенов должен совпадать с ключом API, иначе ингестор отбросит все результаты; на стенде он задан в `deploy/compose.yaml` (`APX_JOB_TOKEN_KEY`), пароль пользователя — `VALKEY_QUEUE_INGEST_PASSWORD`.

Тесты воркера, которым нужны Docker и образ тулчейна (`-m image`: песочница, оркестратор), запускает `just toolchain-test`; под gVisor — с `JUDGE_SANDBOX_RUNTIME=runsc`. Остальные (`just test`) работают с Valkey в контейнере и S3 через moto.

## Судья: CLI `judge`

`judge` ставится вместе с окружением `judge` (`just install`) и запускается через Poetry:

```sh
poetry -C judge run judge new my-task --dir ../problems          # пакет из шаблона
poetry -C judge run judge validate ../problems/my-task          # полная проверка пакета (Docker)
poetry -C judge run judge validate --schema-only ../problems    # только problem.yaml, без Docker
poetry -C judge run judge run ../problems/my-task --solution x.sv --kind submit --seed 41917
poetry -C judge run judge pack ../problems/my-task              # my-task-1.tar.zst и content_hash
poetry -C judge run judge schema                                # JSON Schema problem.yaml в stdout
poetry -C judge run judge schema tb-result                      # JSON Schema записи протокола тестбенча
```

Этапы выполняются в контейнере образа тулчейна с ограничениями песочницы: нужен Docker и собранный образ (`just toolchain-build`, или `--image`/`JUDGE_TOOLCHAIN_IMAGE` с опубликованным профилем). `--no-docker` запускает инструменты на хосте — только для доверенного кода и если инструменты установлены. Лимиты берутся из `config/resource-classes.yaml` репозитория, в котором лежит пакет.

- `validate` печатает по строке на проверку (`ok`, `FAIL` с причиной, `--` — пропущено) и итог; код выхода 1, если хоть один пакет невалиден, 2 — ошибка окружения. Сиды эталонов видны в строках и детерминированы по `id@version`: упавший прогон повторяется через `judge run --seed`. `-v` показывает консоль этапов, `--seeds N` задаёт число сидов.
- `validate --schema-only` проверяет только `problem.yaml`: структуру и типы полей, перекрёстные ссылки на этапы, совпадение `id` с именем каталога, с путём к полю в каждой ошибке (`interface.ports[0].dir: Input should be 'input', 'output' or 'inout'`).
- `run` печатает консоль, как на сайте, и вердикт; в `--out` (по умолчанию `./out`) — `events.jsonl`, `result.json` и артефакты этапов, например окно трассы `sim_run/trace.fst`. Код выхода 0 при `accepted`/`accepted_with_warnings`, 1 при другом вердикте.

Что проверяет `validate` и как устроены `pack` и `new` — в [judge.md](judge.md).

Модель манифеста — `judge/src/judge/core/package.py` (Pydantic, строгие типы, неизвестные поля запрещены). JSON Schema генерируется из неё: после правки модели выполните `just schemas` и закоммитьте `judge/schemas/problem.schema.json` — тест `test_committed_json_schema_is_up_to_date` падает, если файл устарел. YAML читается безопасным загрузчиком, повторяющиеся ключи — ошибка.

Протокол результатов тестбенча (specs/06 §3.3) разбирает `judge/src/judge/languages/systemverilog/tbproto.py`: `parse_result` — файл результатов с лимитом размера, проверкой схемы и порядка записей (нарушение — `ProtocolError`, этап получит `OUTPUT_INVALID`), `split_progress` — строки прогресса `@@apx:<nonce>` в выводе симуляции. Модели записей — источник правды, схема `judge/schemas/tb-result.schema.json` генерируется `just schemas` и проверяется тестом так же, как схема манифеста. Сторона тестбенча — библиотека `toolchain/sv/apx_tb_pkg.sv` в образе тулчейна; совместимость обеих сторон проверяют тесты образа (`toolchain/tests/test_apx_tb_pkg.py`).

## JS

Корень репозитория — pnpm workspace: в корне только `package.json` (версии pnpm и Node), `pnpm-workspace.yaml` и общий `pnpm-lock.yaml`. `pnpm install` в корне ставит зависимости всех пакетов. Зависимость добавляется в пакет: `pnpm -C web add <пакет>` (`-D` для инструментов).

Фронтенд — Next.js-приложение в `web/`, его устройство описано в [frontend.md](frontend.md). Инструменты и их настройки живут в пакете, который они проверяют. Для `web/`: eslint (`web/eslint.config.mjs`: правила Next.js `core-web-vitals`, typescript-eslint `strict` и `eslint-plugin-storybook` для историй), Storybook (`web/.storybook/`), Vitest (`web/vitest.config.mts`), prettier (`web/.prettierrc.json`) и строгий `web/tsconfig.json` (`pnpm -C web typecheck`). Типизированный клиент API — `web/src/lib/api/` ([api.md](api.md)); сгенерированный `schema.d.ts` исключён из eslint и prettier. Скрипты сборки зависимостей pnpm 11 не запускает; пакеты, чьи скрипты сознательно пропущены, перечислены в `allowBuilds` файла `pnpm-workspace.yaml`. Новый пакет со скриптом остановит `pnpm install`, и решение о нём нужно записать туда же. TypeScript закреплён на 6.0: typescript-eslint пока не поддерживает 7.x.

## Git-хуки

`pre-commit install` (входит в `just install`) подключает хуки из `.pre-commit-config.yaml`: базовые проверки файлов (в том числе YAML, TOML и JSON), ruff, mypy затронутых проектов, сверка lock-файлов, eslint и prettier для `web/` при изменениях в нём. Python- и JS-хуки запускают инструменты из окружений проектов, поэтому их версии совпадают с lock-файлами; перед первым коммитом нужен `just install`.

Прогнать хуки по всем файлам: `pre-commit run --all-files`.
