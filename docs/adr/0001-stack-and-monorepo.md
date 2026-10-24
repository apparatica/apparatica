# ADR-0001. Стек и структура монорепо

- Статус: Принято
- Дата: 2026-10-24
- Связано: бриф §7, §8; 03-architecture.md

## Контекст
Бриф рекомендует популярный стек, хорошо знакомый ИИ-агентам, со строгой типизацией и contract-first API. Судья, CLI и воркер должны быть одной реализацией. Дизайн готов под Next.js + Tailwind + shadcn/ui.

## Решение
- **Фронтенд:** Next.js 16 (App Router) + React 19 + TypeScript strict + Tailwind 4 (тема из handoff `tailwind.theme.ts` написана для v3 и переносится в CSS-блок `@theme` поверх `tokens.css`) + shadcn/ui (Radix) + TanStack Query + next-intl (`ru`) + Lucide + Motion. Monaco через `@monaco-editor/react`. Клиент API — `openapi-typescript` + `openapi-fetch` (лёгкий, типы из `openapi.json`, без кодогенерации классов); моки для разработки фронтенда до готовности бэкенда — MSW.
- **Контракт API — code-first:** источник правды — Pydantic-схемы и роуты FastAPI; `backend/openapi.json` генерируется и коммитится, CI проверяет актуальность; фаза начинается с PR контракта с роутами-заглушками (specs/05 §0). Рукописный OpenAPI параллельно с кодом не поддерживается: два контракта неизбежно расходятся.
- **Бэкенд:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.1 async (asyncpg), Alembic, SQLAdmin, Authlib, `pydantic-settings`, structlog.
- **Судья и воркер:** Python 3.13, тот же язык, что и бэкенд; pyslang для статического анализа; Dramatiq ≥ 2.2 (ADR-0002); песочница через помощник `apx-sandboxd` (specs/07 §5.3).
- **Данные:** PostgreSQL 17; Valkey 8 (BSD-3, Redis-совместимый; Redis ≥ 7.4 распространяется под RSAL/SSPL/AGPL) — два инстанса: очередь и кэш; объектное хранилище Garage (ADR-0013). В тексте «Redis Streams», `RedisBroker` и т. п. обозначают протокол, который Valkey реализует.
- **Готовые библиотеки вместо своего кода:** rate limit — `limits` (основа slowapi) с хранилищем Valkey; диагностики Verilator — `--diagnostics-sarif`; диагностики slang — структурированные из pyslang.
- **Хостинг репозитория:** GitHub — код, issues, PR, GitHub Actions, образы в GHCR (решение ОВ-17).
- **Инструменты разработки:** Poetry 2.x (Python), pnpm (JS), ruff, mypy strict, import-linter, eslint, prettier, Vitest, Playwright, pre-commit; GitHub Actions; `just` как точка входа (`just up`, `just test`, `just openapi`).
- **Монорепо** со структурой из 03 §6; задачи — в `problems/` того же репозитория.
- **Reverse proxy:** Caddy (автоматический TLS, HTTP/2, простой конфиг SSE).
- Версии закрепляются в lock-файлах; минимальные версии выше — на момент 2026-10.

## Последствия
- Один язык (Python) для API, судьи, воркера и CLI — общие Pydantic-модели пакета задачи и событий.
- Next.js даёт SSR для SEO и OG-картинок «из коробки» (`next/og`).
- Два пакетных менеджера (Poetry, pnpm) — приемлемо, обёрнуто в `just`.
- **Poetry в монорепо.** Workspaces у Poetry нет, поэтому у каждого Python-пакета (`judge`, `backend`, `worker`) свой `pyproject.toml` (формат PEP 621, секция `[project]`) и свой `poetry.lock`. `backend` и `worker` подключают `judge` как path-зависимость (`develop = true`): правка судьи сразу видна в API и воркере без публикации пакета. В Docker-образах зависимости ставятся `poetry install --only main --no-root` в отдельной стадии сборки.
- Три lock-файла могут разойтись в версиях общих библиотек (pydantic, redis). Защита — Renovate обновляет их одной группой, а CI-скрипт `just check-locks` сравнивает версии общих зависимостей и падает при расхождении.
- Задачи в монорепо упрощают старт и CI; вынос в отдельный репозиторий позже — изменение CI и команды импорта, формат пакета не меняется.

## Альтернативы
- **uv** вместо Poetry — быстрее и поддерживает workspaces с одним lock-файлом, но команда лучше знает Poetry; переход возможен позже без изменения структуры каталогов.
- React + Vite SPA с отдельным рендером OG — проще деплой фронтенда, но SSR страниц задач и OG придётся делать отдельно.
- Celery вместо Dramatiq — см. ADR-0002.
- orval вместо openapi-typescript — генерирует хуки TanStack Query, но тяжелее и сильнее связывает фронтенд с генератором; можно перейти позже без изменения API.
- Отдельный репозиторий задач с первого дня — лишняя синхронизация версий судьи и задач в Ф0.
