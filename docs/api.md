# API

HTTP API платформы: где лежит контракт, как его менять и как его использует фронтенд. Требования к API и список эндпоинтов по фазам — [specs/05](../specs/05-api.md).

## Контракт

Источник правды — код бэкенда: Pydantic-схемы (`schemas.py` модулей) и роуты FastAPI (`api.py`). Из них FastAPI строит документ OpenAPI 3.1, а он коммитится в двух видах:

| Файл | Что это | Чем создаётся |
|---|---|---|
| `backend/openapi.json` | документ OpenAPI | `apparatica openapi` |
| `web/src/lib/api/schema.d.ts` | типы TypeScript для клиента | `openapi-typescript` из `openapi.json` |

Оба файла пересоздаёт одна команда:

```sh
just openapi
```

Вручную файлы не правятся. Устаревший файл ловят проверки:
- `backend/tests/test_openapi.py` сравнивает `openapi.json` с документом, построенным из кода (`just test`, job Python в CI);
- `just check-api` сравнивает `schema.d.ts` с `openapi.json` (job JS в CI);
- `just typecheck-js` находит код фронтенда, который не совпадает с новыми типами.

Работающий сервер отдаёт тот же документ на `/api/v1/openapi.json` и интерактивную документацию на `/api/v1/docs`.

## Как изменить API

1. Измените схемы и роуты в коде бэкенда.
2. Выполните `just openapi`.
3. Закоммитьте код вместе с `openapi.json` и `schema.d.ts`. На ревью дифф `openapi.json` показывает изменение контракта.

Фаза с новыми эндпоинтами начинается с PR контракта (`T<фаза>.0`, specs/05 §0): схемы, роуты-заглушки с ответом `501 NOT_IMPLEMENTED`, `openapi.json`, типы клиента и моки.

## Что объявляется в коде явно

FastAPI не выводит из кода всё, что нужно клиенту:

- **Ошибки.** Все ошибки — `application/problem+json`. В компонентах OpenAPI схема ошибки называется `Error`; имя `Problem` занято задачами. Любая операция может вернуть `500 INTERNAL`: этот ответ добавляется ко всем роутерам при подключении в `apparatica.main`. Остальные ошибки роут перечисляет сам: `responses=problem_responses(ErrorCode.NOT_FOUND, …)` из `apparatica.core.errors`. Роут с параметрами объявляет `VALIDATION_ERROR` (422), иначе FastAPI вставит в схему свой ответ 422 в другом формате; тест падает, если в документе есть ошибка не в формате `problem+json`.
- **Фаза.** Каждая операция помечается `openapi_extra={"x-phase": N}`.
- **Имена операций.** `operationId` — имя функции-обработчика (`list_problems`, `create_submission`). Переименование обработчика меняет контракт.

## Общие правила

Описаны в specs/05 §1–2 и реализованы так:

- **Префикс** `/api/v1`, JSON, `snake_case`, время — ISO 8601 с часовым поясом, идентификаторы — UUIDv7 строкой.
- **Числа больше 2⁵³** передаются строкой: так передаётся `seed` отправки (63 бита).
- **Ошибки.** `code` — стабильный машинный код. По нему фронтенд показывает текст из `messages/ru.json`, подставляя `params`. Поля `title` и `detail` — английские и предназначены для разработчиков.
- **Кэш.** Публичные данные отдаются с `ETag` и `Cache-Control: public, max-age=60, stale-while-revalidate=300`; на `If-None-Match` сервер отвечает 304. Версия задачи неизменяема: `public, max-age=31536000, immutable`. Ответы про отправки — `private, no-store`.

## Отправки (Ф0)

`POST /api/v1/submissions` создаёт Run или Submit и отвечает `202` с отправкой и заголовком `Location`. В Ф0 воркеров нет: отправка остаётся в статусе `queued`.

1. **Размер кода** проверяется по `limits.solution` из `config/limits.yaml`, то есть по тем же значениям, что отдаёт `GET /config`. Байты считаются в UTF-8, строки — по `\n`. Превышение — `413 CODE_TOO_LARGE`, в `params` лимиты и фактические значения. Код с символом NUL или с одиночным суррогатом — `422`.
2. **Версия задачи.** Отправить можно только на текущую версию опубликованной задачи. Иначе `409 PROBLEM_VERSION_OUTDATED` с `params.current_version`; неизвестная задача — `404`.
3. **Профиль тулчейна.** Отправка проверяется профилем по умолчанию для языка задачи. Если такого профиля нет — `503 JUDGE_UNAVAILABLE`. Профили регистрирует `apparatica-admin toolchain add` ([development.md](development.md#профили-тулчейна)).
4. **Сид.** Для каждой отправки выбирается случайное 63-битное число. Версия задачи, профиль и сид вместе делают прогон воспроизводимым (specs/04 §1).
5. **Очередь.** После коммита отправка передаётся в очередь `judge.<resource_class>` вместе с токеном задания. В Ф0 очереди ещё нет, и задание только пишется в лог; Dramatiq подключит T1.1.

**Токен задания** (specs/07 §5.3) — подписанные HMAC-SHA256 поля `{submission_id, attempt_max, exp}` в формате `v1.<payload>.<mac>` (base64url). Ключ — `APX_JOB_TOKEN_KEY`, срок жизни — `APX_JOB_TOKEN_TTL_S` ([configuration.md](configuration.md)). Ингестор (Ф1) примет результат воркера только с действительным токеном этой отправки.

`GET /api/v1/submissions/{id}` возвращает отправку с этапами (в порядке конвейера) и артефактами. Файл результатов тестбенча (`tb_result`) в списке артефактов не показывается: в нём ожидаемые значения скрытых тестов (specs/07 §4.4). Пока нет гостевой cookie (T1.7), отправку видит любой, кто знает её id.

## Клиент во фронтенде

`web/src/lib/api/client.ts` создаёт типизированный клиент `openapi-fetch` по типам из `schema.d.ts`:

```ts
import { createApiClient } from "./lib/api/client"; // путь от web/src

const api = createApiClient();
const { data, error } = await api.GET("/api/v1/problems/{slug}", {
  params: { path: { slug: "sync-fifo" } },
});
// data — ProblemDetail, error — ApiError (problem+json)
```

Пути в схеме начинаются с `/api/v1`, поэтому `baseUrl` — origin API; пустая строка означает тот же origin, что у сайта. Схемы доступны как `Schemas["ProblemDetail"]`, ошибка — `ApiError`, коды — `ErrorCode`.
