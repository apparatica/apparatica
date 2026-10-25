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
| `just typecheck` | mypy `--strict` в каждом Python-проекте, для `scripts/` и Python-кода `toolchain/` (с `--platform linux`) |
| `just test` | `test-py`: pytest в каждом Python-проекте и тесты `scripts/` |
| `just check-locks` | `poetry check --lock` в каждом проекте и сверка версий общих зависимостей между тремя `poetry.lock` |
| `just check-licenses` | лицензии зависимостей Python (`check-licenses-py`) и JS (`check-licenses-js`) по политике |
| `just check` | `check-locks`, `check-licenses`, `lint`, `typecheck`, `test` |
| `just validate-problems` | `judge validate` всех пакетов `problems/` в образе тулчейна (нужен Docker) |
| `just schemas` | перегенерирует JSON Schema из моделей судьи: `problem.yaml` и записи протокола тестбенча (`judge/schemas/`) |
| `just toolchain-build` | собирает образ тулчейна `apparatica-toolchain:dev` |
| `just toolchain-test` | тесты образа: pytest на хосте, команды через `docker exec` в контейнере с ограничениями песочницы |

Рецепты `justfile` работают и в sh (Linux, macOS, CI), и в PowerShell 7 (Windows).

## CI

GitHub Actions, `.github/workflows/ci.yml`, на GitHub-hosted раннерах `ubuntu-24.04`. Запускается на push в `master`, на каждый pull request и вручную. Два параллельных job'а вызывают те же рецепты `just`, что и локальная проверка:

| Job | Шаги |
|---|---|
| Python | `install-py`, `check-locks`, `lint-py`, `lint-imports`, `typecheck`, `test-py`, `check-licenses-py` |
| JS | `install-js`, `lint-js`, `check-licenses-js` |

Образ тулчейна собирает и публикует отдельный workflow `.github/workflows/toolchain.yml` — при изменениях в `toolchain/` и в коде судьи, чьи тесты против образа он прогоняет; публикует только при изменении входов образа (подробности — [toolchain/README.md](../toolchain/README.md)).

Задачи проверяет workflow `.github/workflows/problems.yml`: `judge validate --determinism` в образе тулчейна, собранном из той же ревизии (кэш слоёв общий с `toolchain.yml`). Какие пакеты проверять, решает `scripts/changed_problems.py`: на pull request и push — изменённые пакеты `problems/<id>/`; если изменились судья (`judge/src`, `judge/poetry.lock`), образ (`toolchain/`), классы ресурсов или сам workflow — все пакеты (регрессия эталонов, мутантов и детерминизма). Раз в неделю и вручную (`workflow_dispatch`) проверяются все пакеты. Локально то же самое — `just validate-problems`. Чтобы PR с невалидным пакетом нельзя было слить, job `Validate packages` нужно сделать обязательной проверкой в настройках защиты ветки `master`.

Python 3.13 и Poetry (версия в `POETRY_VERSION` workflow) ставятся в job'е, виртуальные окружения кэшируются по хэшу `poetry.lock`; Node 24 и pnpm — из `packageManager`, кэш pnpm-store. Сторонние actions закреплены по SHA коммита, версия — в комментарии. Unit-тесты TS добавятся в JS job вместе с Vitest (T0.20).

## Архитектурные контракты

import-linter проверяет границу ядра и языковых модулей (ADR-0011, NFR-MAINT-04). Контракты лежат в `[tool.importlinter]` проекта, чьё окружение их проверяет:

| Проект | Контракт |
|---|---|
| `judge` | `judge.core` не импортирует `judge.languages` |
| `backend` | `apparatica` не импортирует `judge.languages` ни напрямую, ни через другие модули `judge` |
| `backend` | `apparatica.core` не импортирует остальные модули бэкенда (specs/03 §3; пока — `apparatica.main` и `apparatica.cli`) |

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
web/        фронтенд (пакет pnpm workspace; каркас Next.js — T0.20)
.github/    CI (GitHub Actions)
toolchain/  образ тулчейна песочницы: Dockerfile, versions.lock, apx-run, apx-verilate, apx_tb_pkg, тесты образа
config/     конфигурация: классы ресурсов судьи (resource-classes.yaml)
problems/   пакеты задач, CC BY-SA 4.0
scripts/    служебные скрипты: сверка lock-файлов и лицензий, политика лицензий
docs/       проектная документация
specs/      спецификация и план
brief/      исходные материалы заказчика (не редактируются)
```

Остальные каталоги из [specs/03 §6](../specs/03-architecture.md) (`config/`, `deploy/`, `tests/`) появляются вместе с задачами, которые их наполняют.

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
- `problems` — таблицы `tags`, `problems`, `problem_versions`, `reference_solutions`;
- `submissions` — таблицы `toolchain_profiles`, `submissions`, `stage_results`, `artifacts`.

Модули зависят друг от друга в одну сторону: `submissions → problems → core`. Это контракт import-linter (`[tool.importlinter]` в `backend/pyproject.toml`).

```sh
poetry -C backend run apparatica serve --reload   # http://127.0.0.1:8000/api/v1/docs
poetry -C backend run apparatica migrate          # alembic upgrade head
```

Нужен Postgres 17+ по `APX_DATABASE_URL` (стенд docker compose — T0.19); без него API стартует, но `GET /health` отвечает 503. Настройки и файлы `config/` — [configuration.md](configuration.md).

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

### Тесты

Тесты бэкенда (`backend/tests`) поднимают приложение через `TestClient`. Где нужна только связь с БД, вместо Postgres используется SQLite в памяти (`aiosqlite`).

Тесты схемы и миграций (`test_db.py`, `test_cli.py`) работают с настоящим Postgres:
- **Сервер.** Fixture `postgres` поднимает его через testcontainers один раз на сессию. Нужен Docker. Без Docker тесты пропускаются, а в CI (переменная `CI`) падают.
- **Изоляция.** Миграции применяются один раз к базе-шаблону. Каждый тест получает свою копию (`CREATE DATABASE … TEMPLATE`).
- **Образ.** По умолчанию `postgres:17-alpine`. Если Docker Hub недоступен, образ задаётся через `APX_TEST_POSTGRES_IMAGE`, например `mirror.gcr.io/library/postgres:17-alpine`.

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

Инструменты и их настройки живут в пакете, который они проверяют. Для `web/`: eslint (`web/eslint.config.mjs`, typescript-eslint `strict`), prettier (`web/.prettierrc.json`) и строгий `web/tsconfig.json`. TypeScript закреплён на 6.0: typescript-eslint пока не поддерживает 7.x.

## Git-хуки

`pre-commit install` (входит в `just install`) подключает хуки из `.pre-commit-config.yaml`: базовые проверки файлов (в том числе YAML, TOML и JSON), ruff, mypy затронутых проектов, сверка lock-файлов, eslint и prettier для `web/` при изменениях в нём. Python- и JS-хуки запускают инструменты из окружений проектов, поэтому их версии совпадают с lock-файлами; перед первым коммитом нужен `just install`.

Прогнать хуки по всем файлам: `pre-commit run --all-files`.
