# 05. API

## 0. Источник правды и порядок работы

**Источник правды контракта — код бэкенда:** Pydantic-схемы и сигнатуры роутов FastAPI. Рукописного контракта, который поддерживается параллельно с кодом, нет.

- FastAPI генерирует OpenAPI 3.1; команда `just openapi` выгружает его в `backend/openapi.json` (JSON — формат FastAPI по умолчанию). Файл коммитится.
- CI заново генерирует файл и падает, если закоммиченная версия отличается от кода.
- TS-клиент (`openapi-typescript` + `openapi-fetch`) генерируется из `backend/openapi.json` и тоже коммитится; расхождение API и фронтенда ловит проверка типов.
- **PR контракта.** Каждая фаза с новыми эндпоинтами начинается с PR, который содержит только контракт: Pydantic-схемы, роуты с заглушками (ответ 501 `NOT_IMPLEMENTED`), сгенерированные `openapi.json` и TS-клиент, моки для фронтенда (MSW-обработчики на сгенерированных типах). После его слияния фронтенд и реализация бэкенда идут параллельно. Задачи — `T<фаза>.0` в [плане](plan/roadmap.md).
- Изменение контракта после PR контракта — отдельный PR или явная часть PR реализации; ревью проверяет дифф `openapi.json`.

Что FastAPI не выводит сам и что объявляется в коде явно:

- **SSE.** Для `text/event-stream` FastAPI не знает модели событий. Схема `SubmissionEvent` подключается к эндпоинту через `responses=` (`content: text/event-stream`) и регистрируется в `components`, чтобы попасть в TS-клиент.
- **Ошибки.** Ответы `application/problem+json` (§2) объявляются общим набором `responses=` на роутерах, иначе их не будет ни в схеме, ни в клиенте.
- **Фазы.** Операции помечаются расширением `x-phase` через `openapi_extra`, чтобы было видно, к какой фазе относится эндпоинт.

**Черновик** [api/openapi.yaml](api/openapi.yaml) написан до кода и служит исходными данными для PR контракта Ф0 и следующих фаз. Он не поддерживается параллельно с кодом и удаляется, когда сгенерированный `openapi.json` покроет все описанные в нём эндпоинты (последний — PR контракта Ф5, T5.0). До удаления при расхождении прав код; черновик правится, только если меняется замысел эндпоинта ещё не начатой фазы.

## 1. Общие правила

- База — `/api/v1`. Тот же origin, что и сайт (через proxy).
- JSON, `snake_case`. Время — ISO 8601 UTC. ID — UUIDv7 строкой.
- Пагинация: `?page=1&per_page=12` (максимум 100), ответ `{items, page, per_page, total}`. Ленты истории — курсор `?cursor=`.
- Аутентификация: cookie сессии (`ap_session`). Гость — cookie `ap_guest` (подписанная). Изменяющие запросы требуют заголовок `X-CSRF-Token` со значением cookie `ap_csrf`.
- Кэш: публичные GET отдают `ETag` и `Cache-Control: public, max-age=60, stale-while-revalidate=300`; ответы, зависящие от пользователя, — `private, no-store`. Данные версии задачи неизменяемы: `GET /problems/{slug}/versions/{version}` — `immutable, max-age=31536000`.

## 2. Ошибки

RFC 9457 `application/problem+json`:

```json
{
  "type": "https://apparatica.app/errors/rate-limited",
  "title": "Too many submissions",
  "status": 429,
  "code": "RATE_LIMITED",
  "detail": "Guest limit is 10 checks per hour",
  "params": {"limit": 10, "window_s": 3600, "retry_after_s": 761},
  "request_id": "01JB…"
}
```

`code` — стабильный машинный код; фронтенд показывает текст по коду из `messages/ru.json`, подставляя `params`. `title`/`detail` — английские, для разработчиков.

| Код | HTTP | Когда |
|---|---|---|
| `VALIDATION_ERROR` | 422 | неверные параметры (поле `errors[]`) |
| `NOT_FOUND` | 404 | задача, версия, отправка, решение, пользователь; неизвестный путь |
| `METHOD_NOT_ALLOWED` | 405 | метод не поддерживается путём |
| `UNAUTHENTICATED` | 401 | нужен вход |
| `FORBIDDEN` | 403 | нет прав |
| `CSRF_FAILED` | 403 | нет или неверный CSRF-токен |
| `RATE_LIMITED` | 429 | лимит проверок или запросов; `retry_after_s` |
| `CAPTCHA_REQUIRED` | 428 | нужна капча; `challenge_url`, `reason` (`always`, `frequent`, `invalid`), при частых проверках `retry_after_s` |
| `CODE_TOO_LARGE` | 413 | код больше лимита |
| `PROBLEM_VERSION_OUTDATED` | 409 | отправка на не текущую версию (разрешено только для rejudge) |
| `HEAVY_NOT_ALLOWED` | 403 | тяжёлая задача для гостя |
| `REFERENCE_LOCKED` | 403 | эталон закрыт до своего Accepted |
| `SOLUTION_LOCKED` | 403 | код решения закрыт политикой видимости |
| `SUBMISSION_FINISHED` | 409 | отмена завершённой отправки |
| `NOT_IMPLEMENTED` | 501 | эндпоинт объявлен в PR контракта, но ещё не реализован (§0) |
| `JUDGE_UNAVAILABLE` | 503 | очередь недоступна |
| `INTERNAL` | 500 | `request_id` для поддержки |

## 3. Эндпоинты по фазам

| Метод и путь | Фаза | Назначение |
|---|---|---|
| `GET /health`, `GET /config` | Ф0 | здоровье; feature flags, лимиты, провайдеры входа, уровни |
| `GET /problems` | Ф0 | каталог с фильтрами `difficulty`, `tag`, `q`, `sort`; процент принятых — Ф1; фильтр `status` — Ф2 для вошедших (статусы гостя хранит браузер, по ним фильтрует он, FR-CAT-03) |
| `GET /problems/{slug}` | Ф0 | текущая версия: условие, шаблон, интерфейс, статистика |
| `GET /problems/{slug}/versions/{version}` | Ф0 | конкретная версия |
| `GET /tags` | Ф0 | справочник тегов |
| `POST /submissions` | Ф0 | создать Run/Submit (в Ф0 — без воркера, статус `queued`) |
| `GET /submissions/{id}` | Ф0 | отправка, этапы, тесты, артефакты |
| `GET /submissions/{id}/events` | Ф1 | SSE (07 §4) |
| `POST /submissions/{id}/cancel` | Ф1 | отмена |
| `GET /submissions` | Ф1 | свои отправки (гость — по cookie), фильтр `problem` |
| `GET /submissions/{id}/artifacts/{kind}` | Ф1 | 302 на presigned URL |
| `POST /submissions/{id}/waveform` | Ф1 | пересоздать или записать полную трассу |
| `GET /captcha/challenge` | Ф1 | ALTCHA-задача |
| `GET /auth/providers` | Ф2 | доступные провайдеры |
| `GET /auth/{provider}/login`, `GET /auth/{provider}/callback` | Ф2 / Ф4 | OAuth/OIDC: GitHub — Ф2; VK ID, Яндекс ID, Google — Ф4 |
| `POST /auth/telegram` | Ф4 | данные Telegram Login |
| `POST /auth/email/request`, `POST /auth/email/verify` | Ф2 | magic link |
| `POST /auth/logout`, `POST /auth/logout-all` | Ф2 | выход |
| `GET /me`, `PATCH /me`, `DELETE /me`, `GET /me/export` | Ф2 | свой аккаунт |
| `GET /me/identities`, `DELETE /me/identities/{id}` | Ф4 | привязанные провайдеры |
| `GET /me/dashboard` | Ф4 | данные дашборда |
| `GET /me/drafts/{slug}`, `PUT /me/drafts/{slug}` | Ф2 | черновики |
| `POST /me/guest-import` | Ф4 | перенос гостевых отправок и черновиков |
| `GET /users/{nick}`, `GET /users/{nick}/activity`, `GET /users/{nick}/solutions` | Ф2 / Ф4 / Ф3 | профиль, heatmap, решения |
| `GET /home` | Ф4 | данные гостевого дашборда: задача дня, популярные, топ |
| `GET /problems/{slug}/leaderboard` | Ф3 | рейтинг решений; `group`, `around=me` |
| `GET /problems/{slug}/solutions` | Ф3 | список решений; `sort=delay\|area\|new` |
| `GET /problems/{slug}/reference` | Ф3 | эталоны или `REFERENCE_LOCKED` |
| `GET /solutions/{id}` | Ф3 | публичное решение |
| `GET /leaderboard` | Ф3 | общий рейтинг; `around=me` |
| `POST /problems/{slug}/reports` | Ф5 | жалоба |
| `/admin/*` | Ф5 | SQLAdmin (HTML), не часть OpenAPI |

OG-картинки рендерит web: `/problems/[slug]/opengraph-image`, `/solutions/[id]/opengraph-image`.

## 4. SSE

`GET /submissions/{id}/events` — `text/event-stream`. Каждое событие:

```
id: 1729771927123-0
event: log
data: {"stage":"lint","ch":"out","text":"%Warning-WIDTHTRUNC: sync_fifo.sv:24:17: ...\n"}
```

Типы и поля — 07 §4.1. Итоговый статус клиент берёт только из события `finalized`. Схемы событий есть в OpenAPI (`components/schemas/SubmissionEvent`) для генерации типов, хотя сам эндпоинт описан как поток. Доступ: автор отправки (пользователь или гость по cookie), модератор. События отправки принадлежат её автору; публичное решение показывает только итоговые результаты, не стрим.

## 5. Видимость полей отправки

| Поле | Автор | Другие (принятое публичное решение) |
|---|---|---|
| `code` | да | после собственного Accepted по задаче — пользователя или гостя (иначе `null` и `code_locked: true`) |
| `stages[].metrics` | да | только `synth`, `formal` |
| `stages[].summary.tests` открытых | да | нет |
| скрытые тесты | только счётчики | нет |
| логи, FST | да | нет |
| `seed` | да | нет |
