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

Пример установки на Windows: `winget install Casey.Just`, `pipx install pre-commit`; на macOS — `brew install just pre-commit`; на Linux — пакетный менеджер дистрибутива или `pipx install pre-commit` и `cargo install just`.

Docker понадобится для образа тулчейна и стенда (`just up`) — эти команды появятся в T0.3 и T0.19.

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
| `just install` | ставит зависимости Python и JS, подключает git-хуки |
| `just lint` | ruff (линт и проверка форматирования); eslint и prettier `--check` в `web/` |
| `just fmt` | применяет ruff format, безопасные исправления ruff и prettier в `web/` |
| `just typecheck` | mypy `--strict` в каждом Python-проекте и для `scripts/` |
| `just test` | pytest в каждом Python-проекте |
| `just check-locks` | `poetry check --lock` в каждом проекте и сверка версий общих зависимостей между тремя `poetry.lock` |
| `just check` | `check-locks`, `lint`, `typecheck`, `test` |

Рецепты `justfile` работают и в sh (Linux, macOS, CI), и в PowerShell 7 (Windows).

## Структура репозитория

```
judge/      пакет судьи и CLI (Poetry, пакет judge)
backend/    FastAPI-приложение и ингестор (Poetry, пакет apparatica)
worker/     воркер и оркестратор песочницы (Poetry, пакет apparatica_worker)
web/        фронтенд (пакет pnpm workspace; каркас Next.js — T0.20)
problems/   пакеты задач, CC BY-SA 4.0
scripts/    служебные скрипты (check_locks.py)
docs/       проектная документация
specs/      спецификация и план
brief/      исходные материалы заказчика (не редактируются)
```

Остальные каталоги из [specs/03 §6](../specs/03-architecture.md) (`toolchain/`, `config/`, `deploy/`, `tests/`, `.github/`) появляются вместе с задачами, которые их наполняют.

## Python-проекты

У `judge`, `backend` и `worker` свои `pyproject.toml` (PEP 621) и `poetry.lock`. `backend` и `worker` подключают `judge` как path-зависимость с `develop = true`: правка судьи сразу видна в них без переустановки.

Зависимость добавляется в конкретный проект: `poetry -C backend add <пакет>` (для инструментов разработки — `--group dev`). Если пакет есть и в других проектах, версии должны совпадать — иначе упадёт `just check-locks`; выровняйте ограничения и выполните `poetry -C <проект> lock`.

Настройки инструментов:
- ruff — общий `ruff.toml` в корне (Python 3.13, длина строки 100); Markdown и `brief/` исключены;
- mypy — `[tool.mypy]` в `pyproject.toml` каждого проекта, `strict = true`;
- pytest — `[tool.pytest.ini_options]` там же.

## JS

Корень репозитория — pnpm workspace: в корне только `package.json` (версии pnpm и Node), `pnpm-workspace.yaml` и общий `pnpm-lock.yaml`. `pnpm install` в корне ставит зависимости всех пакетов. Зависимость добавляется в пакет: `pnpm -C web add <пакет>` (`-D` для инструментов).

Инструменты и их настройки живут в пакете, который они проверяют. Для `web/`: eslint (`web/eslint.config.mjs`, typescript-eslint `strict`), prettier (`web/.prettierrc.json`) и строгий `web/tsconfig.json`. TypeScript закреплён на 6.0: typescript-eslint пока не поддерживает 7.x.

## Git-хуки

`pre-commit install` (входит в `just install`) подключает хуки из `.pre-commit-config.yaml`: базовые проверки файлов (в том числе YAML, TOML и JSON), ruff, mypy затронутых проектов, сверка lock-файлов, eslint и prettier для `web/` при изменениях в нём. Python- и JS-хуки запускают инструменты из окружений проектов, поэтому их версии совпадают с lock-файлами; перед первым коммитом нужен `just install`.

Прогнать хуки по всем файлам: `pre-commit run --all-files`.
