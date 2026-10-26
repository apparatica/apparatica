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
- **Поток SSE.** `GET /submissions/{id}/events` объявлен с классом ответа `EventStreamResponse` (`apparatica.core.http`) и `responses={200: {"model": SubmissionEvent}}`. Так `text/event-stream` в документе ссылается на компонент `SubmissionEvent`, и в TS-клиенте есть типы событий. Встроенный `fastapi.sse.EventSourceResponse` не подходит: с ним обработчик обязан быть генератором и не может ответить ошибкой `problem+json` до начала потока.
- **Фаза.** Каждая операция помечается `openapi_extra={"x-phase": N}`.
- **Имена операций.** `operationId` — имя функции-обработчика (`list_problems`, `create_submission`). Переименование обработчика меняет контракт.

## Общие правила

Описаны в specs/05 §1–2 и реализованы так:

- **Префикс** `/api/v1`, JSON, `snake_case`, время — ISO 8601 с часовым поясом, идентификаторы — UUIDv7 строкой.
- **Числа больше 2⁵³** передаются строкой: так передаётся `seed` отправки (63 бита).
- **Ошибки.** `code` — стабильный машинный код. По нему фронтенд показывает текст из `messages/ru.json`, подставляя `params`. Поля `title` и `detail` — английские и предназначены для разработчиков. В теле ошибки есть все поля схемы `Error`; незаданные равны `null`, как и описывают типы клиента.
- **Кэш.** Публичные данные отдаются с `ETag` и `Cache-Control: public, max-age=60, stale-while-revalidate=300`; на `If-None-Match` сервер отвечает 304. Версия задачи неизменяема: `public, max-age=31536000, immutable`. Ответы про отправки — `private, no-store`.

## Отправки (Ф0)

`POST /api/v1/submissions` создаёт Run или Submit и отвечает `202` с отправкой и заголовком `Location`. В Ф0 воркеров нет: отправка остаётся в статусе `queued`.

1. **Размер кода** проверяется по `limits.solution` из `config/limits.yaml`, то есть по тем же значениям, что отдаёт `GET /config`. Байты считаются в UTF-8, строки — по `\n`. Превышение — `413 CODE_TOO_LARGE`, в `params` лимиты и фактические значения. Код с символом NUL или с одиночным суррогатом — `422`.
2. **Версия задачи.** Отправить можно только на текущую версию опубликованной задачи. Иначе `409 PROBLEM_VERSION_OUTDATED` с `params.current_version`; неизвестная задача — `404`.
3. **Профиль тулчейна.** Отправка проверяется профилем по умолчанию для языка задачи. Если такого профиля нет — `503 JUDGE_UNAVAILABLE`. Профили регистрирует `apparatica-admin toolchain add` ([development.md](development.md#профили-тулчейна)).
4. **Сид.** Для каждой отправки выбирается случайное 63-битное число. Версия задачи, профиль и сид вместе делают прогон воспроизводимым (specs/04 §1).
5. **Очередь.** После коммита отправка передаётся в очередь `judge.<resource_class>` вместе с токеном задания. В Ф0 очереди ещё нет, и задание только пишется в лог; Dramatiq подключит T1.1.

**Токен задания** (specs/07 §5.3) — подписанные HMAC-SHA256 поля `{submission_id, attempt_max, exp}` в формате `v1.<payload>.<mac>` (base64url). Ключ — `APX_JOB_TOKEN_KEY`, срок жизни — `APX_JOB_TOKEN_TTL_S` ([configuration.md](configuration.md)). Ингестор (Ф1) примет результат воркера только с действительным токеном этой отправки.

`GET /api/v1/submissions/{id}` возвращает отправку с этапами (в порядке конвейера) и артефактами. В списке артефактов только виды, которые можно скачать: `log`, `events`, `fst`. Файл результатов тестбенча (`tb_result`) не показывается: в нём ожидаемые значения скрытых тестов (specs/07 §4.4). Пока нет гостевой cookie (T1.7), отправку видит любой, кто знает её id.

## Отправки (Ф1): контракт

PR контракта Ф1 (T1.0) объявил эндпоинты Ф1. Пока задача реализации не влита, эндпоинт отвечает `501 NOT_IMPLEMENTED`, но параметры уже проверяет (`422`). Фронтенд работает с ними через моки ([frontend.md](frontend.md#моки-для-разработки)).

| Эндпоинт | Ответ | Реализация |
|---|---|---|
| `GET /submissions?problem=&cursor=&limit=` | `SubmissionPage`: свои отправки, новые первыми, `next_cursor` и остаток квот `quota` | T1.7 |
| `GET /submissions/{id}/events` | поток событий проверки, см. ниже | T1.5 |
| `POST /submissions/{id}/cancel` | `202` без тела; итог приходит событием `finalized` со статусом `cancelled`. Завершённая отправка — `409 SUBMISSION_FINISHED` | T1.6 |
| `GET /submissions/{id}/artifacts/{kind}?stage=` | `302` на presigned URL файла; истёкший файл — `404` | T1.2b |
| `POST /submissions/{id}/waveform` | `202` с артефактом FST в состоянии `pending`, см. ниже | T1.17 |
| `GET /captcha/challenge` | задача ALTCHA `CaptchaChallenge` | T1.7 |

Что изменилось в эндпоинтах Ф0:

- `POST /submissions` принимает `captcha`: решённую задачу ALTCHA после ответа `428 CAPTCHA_REQUIRED`. Добавлены ошибки `429 RATE_LIMITED` (в `params` — `retry_after_s`) и `403 HEAVY_NOT_ALLOWED`. Ответ `SubmissionCreated` — это отправка и остаток квот `quota`; до T1.7 квоты не считаются, и `quota` равно `null`.
- В отправке появилось поле `eta_s`: оценка ожидания в очереди в секундах.
- У артефакта вместо `expired` теперь `state`: `ready`, `expired` (удалён по сроку хранения), `pending` (FST пересоздаётся), `failed`. Поле `size_bytes` равно `null`, пока файла нет. `waveform` у FST описывает трассу: тест, `scope` (`failure_window` — окно вокруг первого расхождения, `full_test` — весь тест), такты от и до, такт курсора.

**Квоты** (`QuotaStatus`): `checks` — проверки, `waveforms` — пересоздания и полные трассы волн. В каждом окне `limit` и `remaining` считаются за час. `reset_at` — когда освободится следующая попытка; пока попытки есть, оно равно `null`. Остаток квот приходит в ответах `POST /submissions` и `GET /submissions`: этого хватает и для счётчика «Проверок: 3 из 10 в час», и для панели «Лимит исчерпан» с таймером (FR-GST-04).

**Пересоздание волн** (FR-WAV-05). `POST /submissions/{id}/waveform` с `scope: failure_window` пересоздаёт истёкшее окно трассы упавшего теста. С `scope: full_test` и `test` записывается весь тест; это доступно только вошедшим, гостю — `401 UNAUTHENTICATED`. В ответе — артефакт FST в состоянии `pending`. Готовность клиент узнаёт, опрашивая `GET /submissions/{id}`, пока `state` не станет `ready` или `failed`: стрим событий к этому времени давно истёк, а его архив неизменяем. Один FST на этап: полная трасса заменяет окно.

### События проверки

`GET /submissions/{id}/events` — поток Server-Sent Events (specs/07 §4). Каждое событие приходит в трёх полях:

```
id: 1793003352739-1
event: stage_start
data: {"type":"stage_start","stage":"lint","stage_type":"lint","ordinal":1,"attempt":1}
```

`id` — ID записи Valkey Stream (миллисекунды и номер), по нему клиент дочитывает поток после обрыва (`Last-Event-ID` или `?from=`). `event` — тип события, `data` — событие `SubmissionEvent`, объединение по полю `type`:

| `type` | Кто пишет | Что значит |
|---|---|---|
| `queue` | API | позиция в очереди и оценка ожидания |
| `stage_start`, `stage_end` | воркер | этап начат; этап завершён с результатом `StageResult` |
| `log` | воркер | целые строки консоли, каждая с переводом строки, склеенные за ~75 мс или до 8 КБ |
| `heartbeat` | воркер | раз в секунду, пока этап молчит (сборка C++, ABC, SAT) |
| `test` | воркер | тест начат или завершён; тест заменяется по `id` целиком |
| `truncated` | воркер | вывод этапа превысил лимит, этап остановлен |
| `done` | воркер | конвейер попытки завершён |
| `finalized` | ингестор | итоговый статус и `verdict_detail` — последнее событие потока |

У событий воркера есть `attempt`. Событие с новым номером попытки значит, что проверка началась заново, и клиент сбрасывает результаты. Итоговый статус клиент берёт только из `finalized`.

Модели событий воркера — это события пайплайна `judge.core.events` с полем `attempt` (`apparatica.submissions.events`). Тест проверяет, что у каждого события пайплайна есть пара в потоке.

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
