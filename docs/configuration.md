# Конфигурация

Как настраивается бэкенд (`api` и `ingest`): переменные окружения, файлы `config/`, feature flags. Судья и его классы ресурсов — в [judge.md](judge.md).

## Переменные окружения

Читаются при старте процесса (`apparatica.core.settings`, pydantic-settings), префикс `APX_`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APX_ENVIRONMENT` | `development` | `development`, `test` или `production` |
| `APX_DATABASE_URL` | `postgresql+asyncpg://apparatica:apparatica@localhost:5432/apparatica` | URL SQLAlchemy с асинхронным драйвером (`postgresql+asyncpg://…`) |
| `APX_CONFIG_DIR` | `config` | каталог файлов `config/` (ниже), относительно рабочего каталога процесса |
| `APX_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `APX_LOG_FORMAT` | `console` | `json` — одна JSON-запись на строку (production), `console` — читаемые строки |
| `APX_FEATURE_FLAGS_TTL_S` | `30` | сколько секунд процесс кэширует feature flags |
| `APX_HEALTH_TIMEOUT_S` | `2` | таймаут проверки БД в `GET /health` |
| `APX_S3_ENDPOINT_URL` | — | адрес S3 API хранилища (Garage, ADR-0013); не задан — AWS |
| `APX_S3_REGION` | `garage` | регион S3; Garage принимает тот, что задан в его конфигурации |
| `APX_S3_ACCESS_KEY_ID`, `APX_S3_SECRET_ACCESS_KEY` | — | ключ доступа к бакетам |
| `APX_S3_BUCKET_PACKAGES` | `packages` | бакет пакетов задач; в него пишет `apparatica-admin problems import` |
| `APX_S3_BUCKET_ARTIFACTS` | `artifacts` | бакет артефактов проверок: API читает из него журналы событий завершённых проверок, ингестор удаляет истёкшие файлы |
| `APX_S3_PUBLIC_URL` | — | адрес S3 API, по которому хранилище видит браузер (на стенде `http://s3.localhost:8080`): для него API подписывает presigned URL артефактов. Не задан — `APX_S3_ENDPOINT_URL` |
| `APX_ARTIFACT_URL_TTL_S` | `300` | срок жизни presigned URL артефакта ([api.md](api.md#артефакты-и-волны)) |
| `APX_WAVEVIEW_URL` | — | origin сайта просмотрщика волн, как его видит браузер (на стенде `http://waveview.web.localhost:8080`); с версией просмотрщика профиля даёт `waveview_url` отправки ([waveview.md](waveview.md)). Не задан — просмотрщика нет |
| `APX_JOB_TOKEN_KEY` | — | ключ подписи токенов заданий (не короче 32 символов, [api.md](api.md#отправки-ф0)); общий у API и ингестора. API без него не стартует в `production`, а в других окружениях берёт случайный ключ; ингестор без него не стартует никогда |
| `APX_JOB_TOKEN_TTL_S` | `86400` | срок жизни токена задания: ожидание в очереди и все попытки проверки |
| `APX_QUEUE_URL` | — | `redis://` адрес `valkey-queue`: брокер Dramatiq, позиции в очереди и стримы событий проверок ([architecture.md](architecture.md#очередь-проверок)). Обязателен в `production`; в других окружениях без него проверки только пишутся в лог и остаются в очереди, а поток событий отдаётся только для завершённых проверок. Ингестору нужен всегда, с пользователем `ingest` ([security.md](security.md#права-компонентов)) |
| `APX_CACHE_URL` | — | `redis://` адрес `valkey-cache`: счётчики rate limit и квоты волн ([api.md](api.md#авторы-и-лимиты)), кэш сессий. Обязателен в `production`; в других окружениях без него счётчики живут в памяти процесса, а сессии читаются из базы |
| `APX_GUEST_COOKIE_KEY` | — | ключ подписи cookie гостя `ap_guest` (не короче 32 символов). Обязателен в `production`; в других окружениях без него ключ случайный, и после перезапуска гости теряют свои отправки |
| `APX_IP_HASH_SALT` | — | соль HMAC адресов клиентов (не короче 32 символов, NFR-PRIV-01): ключи rate limit и `submissions.client_ip_hash`. Обязательна в `production`; в других окружениях без неё случайная |
| `APX_CAPTCHA_KEY` | — | ключ HMAC задач ALTCHA (не короче 32 символов). Обязателен в `production`; в других окружениях без него ключ случайный, и задачи, выданные до перезапуска, не принимаются |
| `APX_COOKIE_SECURE` | `true` | атрибут `Secure` у cookie; `false` — только для стенда по HTTP |
| `APX_SESSION_TTL_S` | `2592000` | срок сессии вошедшего пользователя с последнего использования (30 дней, FR-AUTH-04; [api.md](api.md#пользователи-и-вход-ф2-контракт)) |
| `APX_SMTP_URL` | — | почтовый сервер писем со ссылками входа: `smtp://` (без TLS — локальный relay, Mailpit), `smtp+starttls://` (STARTTLS обязателен, порт по умолчанию 587) или `smtps://` (TLS сразу, 465); логин и пароль — в URL (`smtps://user:password@host`, спецсимволы в URL-кодировке). Не задан — входа по почте нет ([api.md](api.md#пользователи-и-вход-ф2-контракт)). В production — внешний SMTP-провайдер, а не почта с IP хостинга (R14) |
| `APX_SMTP_TIMEOUT_S` | `10` | таймаут соединения и команд SMTP |
| `APX_MAIL_FROM` | `Apparatica <noreply@localhost>` | заголовок `From` писем; домену отправителя нужны SPF, DKIM и DMARC (specs/09 §1) |
| `APX_PUBLIC_BASE_URL` | — | origin сайта, как его открывают пользователи (`https://apparatica.app`, на стенде `http://localhost:8080`): из него строятся ссылки в письмах и адреса колбэков OAuth (`<origin>/api/v1/auth/<провайдер>/callback`), а не из `Host` запроса, который может подставить кто угодно. Обязателен вместе с `APX_SMTP_URL` и с ключами OAuth-приложения |
| `APX_GITHUB_CLIENT_ID`, `APX_GITHUB_CLIENT_SECRET` | — | ключи OAuth-приложения GitHub (Settings → Developer settings → OAuth Apps; Authorization callback URL — `<APX_PUBLIC_BASE_URL>/api/v1/auth/github/callback`). Заданы оба — есть вход через GitHub, не задан ни один — нет, задан один — API не стартует. Пустое значение — то же, что не задано ([api.md](api.md#пользователи-и-вход-ф2-контракт)) |
| `APX_OAUTH_TIMEOUT_S` | `10` | таймаут каждого запроса к провайдеру при входе (обмен кода на токен, чтение профиля) |
| `APX_INGEST_CONSUMER` | `<hostname>:<pid>` | имя экземпляра ингестора в группе `ingest` стрима `judge:results` и владелец блокировки лидера |
| `APX_WATCHDOG_GRACE_S` | `300` | сколько watchdog ждёт сверх лимитов всех попыток проверки, прежде чем поставить `internal_error` ([architecture.md](architecture.md#ingest)) |
| `APX_PROBLEM_STATS_EVERY_S` | `300` | как часто ингестор пересчитывает процент принятых (`problem_stats`); не больше 600 — FR-CAT-04 |
| `APX_REFERENCE_RUNS_EVERY_S` | `60` | как часто ингестор ищет эталоны текущих версий без прогона на профиле по умолчанию (FR-SYN-04, [architecture.md](architecture.md#ingest)) |
| `APX_REFERENCE_RETRY_S` | `3600` | через сколько повторяется прогон эталона, кончившийся без вердикта (`internal_error`, отмена) |
| `APX_RATING_EVERY_S` | `300` | как часто ингестор пересчитывает общий рейтинг и сохраняет места дня для «за неделю» (FR-LB-05, [architecture.md](architecture.md#ingest)); принятый Submit пересчитывает его сразу |
| `APX_METRICS_PORT` | `9100` | порт `/metrics` ингестора для Prometheus ([ниже](#метрики)); не задан — метрик нет. API отдаёт `/metrics` на своём порту и эту переменную не читает |

Неизвестные переменные с префиксом игнорируются. Секреты (пароль БД в URL, ключи хранилища, ключ токенов заданий, ключ cookie гостя, соль адресов, ключ капчи, `APX_SMTP_URL` с паролем, `APX_GITHUB_CLIENT_SECRET`) передаются только переменными окружения и в репозиторий не попадают.

## Воркер

`apparatica-worker` читает переменные с тем же префиксом (`apparatica_worker.settings`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APX_QUEUE_URL` | `redis://localhost:6379/0` | `valkey-queue`, тот же, что у API, с пользователем `worker` ([security.md](security.md#права-компонентов)) |
| `APX_QUEUES` | `["judge.light", "judge.heavy"]` | очереди основных слотов, JSON-список; например, `["judge.heavy"]` для отдельного пула тяжёлых задач |
| `APX_SLOTS` | половина ядер, не меньше 1 | сколько проверок воркер ведёт одновременно |
| `APX_REJUDGE_SLOTS` | `1` | отдельные слоты для `judge.rejudge`; `0` — воркер не берёт перепроверки |
| `APX_WORKER_ID` | `<hostname>:<pid>` | значение аренды `lease:<id>`, которую держит воркер |
| `APX_SANDBOXD_SOCKET` | `/run/apx-sandboxd/sandboxd.sock` | сокет `apx-sandboxd` |
| `APX_SANDBOX_RUNTIME` | `runsc` | рантайм, который должен использовать `apx-sandboxd`; иначе воркер не стартует. `runc` — только для разработки |
| `APX_RESOURCE_CLASSES` | `config/resource-classes.yaml` | лимиты песочниц по классам ресурсов |
| `APX_PACKAGE_CACHE` | `/var/cache/apparatica/packages` | распакованные пакеты задач |
| `APX_S3_ENDPOINT_URL`, `APX_S3_REGION`, `APX_S3_ACCESS_KEY_ID`, `APX_S3_SECRET_ACCESS_KEY` | —, `garage`, —, — | хранилище; ключ воркера читает `packages`, пишет `artifacts`, читает и пишет `build-cache` |
| `APX_S3_BUCKET_PACKAGES`, `APX_S3_BUCKET_ARTIFACTS` | `packages`, `artifacts` | бакеты пакетов и артефактов |
| `APX_S3_BUCKET_BUILD_CACHE` | `build-cache` | кэш сборки: бинарники симуляции на сутки ([architecture.md](architecture.md#кэш-сборки)) |
| `APX_LOG_LEVEL`, `APX_LOG_FORMAT` | `INFO`, `console` | как у API |
| `APX_METRICS_PORT` | `9100` | порт `/metrics` для Prometheus ([ниже](#метрики)); не задан — метрик нет |

## apx-sandboxd

Демон песочницы на хосте воркера (`apparatica_worker.sandboxd.server`), префикс `APX_SANDBOXD_`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APX_SANDBOXD_SOCKET` | `/run/apx-sandboxd/sandboxd.sock` | unix-сокет, права `0660` |
| `APX_SANDBOXD_SOCKET_GROUP` | — | группа пользователя оркестратора: она может подключаться, а группа `docker` ему не нужна |
| `APX_SANDBOXD_RUNTIME` | `runsc` | рантайм контейнеров; `runc` — только для разработки без gVisor (ADR-0003) |
| `APX_SANDBOXD_IMAGES` | `["ghcr.io/apparatica/toolchain", "apparatica-toolchain"]` | репозитории образов тулчейна, которые можно запускать, JSON-список; тег или digest задаёт клиент |
| `APX_SANDBOXD_MAX_CPUS`, `APX_SANDBOXD_MAX_MEMORY_MB`, `APX_SANDBOXD_MAX_PIDS` | `4`, `8192`, `256` | потолки лимитов контейнера; лимиты сверх них отклоняются |
| `APX_SANDBOXD_MAX_SANDBOXES` | `8` | сколько контейнеров одновременно |
| `APX_SANDBOXD_MAX_LIFETIME_S` | `3600` | контейнер старше этого удаляется |
| `APX_SANDBOXD_LOG_LEVEL`, `APX_SANDBOXD_LOG_FORMAT` | `INFO`, `console` | как у API |

## Файлы `config/`

Данные, которые видит пользователь, и пороги защиты от злоупотреблений — то, что меняется без правки кода. Загружаются при старте и проверяются строго: ошибка в файле останавливает процесс, а не даёт сайт с наполовину пустыми настройками.

| Файл | Кто читает | Содержимое |
|---|---|---|
| `difficulties.yaml` | API → `GET /config` | уровни сложности: `key` (значение `difficulty` в `problem.yaml`), подпись, цветовой токен (`e` — пара `--e`/`--es`); порядок в файле — порядок сортировки каталога (FR-CAT-05) |
| `catalog.yaml` | API → `GET /config` и `GET /problems` | каталог: задач на странице (`per_page`, FR-CAT-01); это и размер страницы `GET /problems` без `per_page` |
| `limits.yaml` | API → `GET /config` и проверка отправок | размер решения (`solution.max_bytes`, `max_lines`) и квоты гостя и пользователя: проверок в час, одновременных, тяжёлых в сутки, перезаписей волн в час (specs/07 §3, [api.md](api.md#авторы-и-лимиты)); самый большой FST, который страница задачи открывает в просмотрщике (`waveforms.view_max_mb`, FR-WAV-02): больший файл только скачивается |
| `rate-limits.yaml` | API; в `GET /config` не попадает | окна rate limit (`limit` событий за `window_s` секунд): запросы к изменяющим эндпоинтам с адреса (`requests_per_ip`) и от автора — пользователя или гостя (`requests_per_author`), сохранения черновиков пользователя (`drafts_per_user`), проверки с адреса (`checks_per_ip`), входы с адреса (`logins_per_ip`), письма со ссылкой входа на один адрес почты (`logins_per_email`, FR-AUTH-05) (NFR-SEC-06); когда нужна капча и сколько работы в задаче ALTCHA (`captcha`, FR-GST-05) |
| `legal.yaml` | API → `GET /config` и первый вход | юридические документы ([legal.md](legal.md)): `draft` — тексты черновые, сайт помечает их; `operator` — `name`, `address`, `email`, их подставляет сайт; `documents.terms` и `documents.privacy` — `version` (дата редакции; её записывает согласие первого входа) и `sha256` текста из `web/content/legal/` (тест проверяет, что правка текста не прошла мимо версии) |
| `resource-classes.yaml` | судья; ингестор — для лимита проверки в watchdog | лимиты песочницы и этапов по классам `light`/`heavy` ([judge.md](judge.md#лимиты)) |
| `retention.yaml` | ингестор | сроки хранения в днях: артефактов по виду отправки (`run`, `submit`) и виду файла (`log`, `events`, `fst`, `tb_result`), `null` — бессрочно (specs/07 §4.4); завершённых гостевых отправок (`guest_submissions_days`, ОВ-13; `null` — не удалять); хэшей адресов клиентов (`client_ip_hash_days`, NFR-PRIV-01) |
| `rating.yaml` | API → `GET /leaderboard` (`formula`); ингестор | формула общего рейтинга (FR-LB-05, ОВ-4, ADR-0006): `formula_version`, очки за решённую задачу по ключам уровней (`solved`: каждый уровень `difficulties.yaml` ровно один раз, иначе процесс не стартует), бонус за 1, 2, 3… место в рейтинге задачи (`places`). Числа меняются вместе с `formula_version`; ингестор пересчитывает рейтинг в течение `APX_RATING_EVERY_S` после перезапуска |

## Feature flags

Известные флаги и их значения по умолчанию объявлены в коде (`apparatica.core.flags.FLAGS`); инстанс переопределяет их записями в таблице `feature_flags`. Запись — это `key`, `enabled` и `rules`. Пока пользователей нет, `rules` (роли, доля пользователей) не применяются. До раздела флагов в админке (Ф5) записи правятся в БД напрямую: `INSERT INTO feature_flags (key, enabled) VALUES ('captcha', true) ON CONFLICT (key) DO UPDATE SET enabled = excluded.enabled, updated_at = now()`. Процесс держит значения в памяти `APX_FEATURE_FLAGS_TTL_S` секунд; если источник переопределений недоступен, остаются последние известные значения (или значения по умолчанию). Переопределения неизвестных флагов игнорируются с записью в лог.

| Флаг | По умолчанию | Что включает |
|---|---|---|
| `auth_email` | вкл. | вход по ссылке из письма, если задан `APX_SMTP_URL`; выключенный провайдер не приходит в `auth_providers`, его эндпоинты отвечают `404` |
| `auth_github` | вкл. | вход через GitHub, если заданы ключи его OAuth-приложения; выключенный — как у `auth_email` |
| `captcha` | выкл. | ALTCHA перед каждой проверкой гостя и перед письмом со ссылкой входа; без флага у проверок — только при частых проверках, у писем капчи нет ([api.md](api.md#авторы-и-лимиты)) |
| `formal_stage` | выкл. | этап формальной проверки и вкладка «Формал» (Ф5) |
| `industrial_mode` | выкл. | индустриальный режим практики (Ф7) |
| `reports` | выкл. | жалобы на задачи и решения (Ф5) |

Флаги остальных провайдеров входа (`auth_<provider>`) появятся вместе с провайдерами (Ф4).

## `GET /api/v1/config`

Всё, что фронтенду нужно до остальных запросов: версия, значения флагов, уровни сложности, размер страницы каталога, лимиты и квоты, провайдеры входа: настроенные и не выключенные флагом `auth_<key>` (`github`, `email`). Ответ публичный: `Cache-Control: public, max-age=60, stale-while-revalidate=300` и `ETag` (на `If-None-Match` — 304), поэтому изменённый флаг виден клиентам в пределах TTL кэша процесса плюс минуты кэша HTTP.

## Логи и request id

Логи пишет structlog в stderr: каждая запись запроса (`event: request`, метод, путь, статус, длительность) и все записи, сделанные во время запроса, содержат `request_id`. Он берётся из заголовка `X-Request-ID` (его ставит proxy; допустимы 8–64 символа `A-Z a-z 0-9 . _ -`) или создаётся как UUIDv7, возвращается в заголовке ответа `X-Request-ID` и в поле `request_id` ошибок `problem+json`.

`submission_id` тоже попадает в контекст записей (NFR-OBS-01): в API — на время запроса с отправкой в пути (`/submissions/{id}/…`) и после создания отправки, в воркере — на время задания (у задания волны ещё `waveform_id`), в ингесторе — на время обработки записи `judge:results`. Записи кода судьи и библиотек через стандартный `logging` получают те же поля.

## Метрики

Метрики Prometheus (NFR-OBS-02, `prometheus_client`): API отдаёт их на своём порту по `/metrics` — вне `/api/v1`, в OpenAPI их нет. Caddy проксирует только `/api/*`, поэтому снаружи `/metrics` недоступен. Ингестор и воркер отдают `/metrics` на `APX_METRICS_PORT`. Этот порт не публикуется: Prometheus ходит к нему по внутренней сети. `apx-sandboxd` без сети метрик не отдаёт. Кроме метрик ниже, у каждого процесса есть стандартные `process_*` и `python_*`. Дашборд Grafana — `deploy/grafana/dashboards/apparatica.json` ([stand.md](stand.md#мониторинг)); тесты бэкенда и воркера проверяют, что каждая метрика дашборда объявлена в коде.

| Метрика | Процесс | Что считает |
|---|---|---|
| `apparatica_http_requests_total{method, route, status}` | API | запросы по шаблону роута (`/api/v1/submissions/{id}`); не совпавшие ни с одним роутом — `route="unmatched"` |
| `apparatica_http_request_duration_seconds{method, route}` | API | время до конца ответа; стримы событий не учитываются |
| `apparatica_api_errors_total{code}` | API | ответы `problem+json` по коду ошибки |
| `apparatica_mail_letters_total{kind, result}` | API | письма, переданные SMTP-серверу (`kind="login-link"`): `sent` или `failed` — сервер недоступен или отказал, причина в логе (`letter not sent`) |
| `apparatica_streams_open` | API | живые стримы событий, которые отдаются сейчас |
| `apparatica_stream_delay_seconds` | API | задержка стрима: от времени id записи в `sub:<id>` (его ставит Valkey) до отправки клиенту; только события, пришедшие, пока клиент слушает |
| `apparatica_queue_waiting{queue}` | ингестор | проверки в очереди: размер `queue:<queue>` |
| `apparatica_queue_oldest_wait_seconds{queue}` | ингестор | сколько ждёт самая старая проверка очереди; 0 — очередь пуста |
| `apparatica_results_pending` | ингестор | записи `judge:results`, ещё не сохранённые в базу |
| `apparatica_checks_finished_total{status}` | ингестор | проверки, получившие финальный статус (`finalized`) |
| `apparatica_ingest_records_total{type, outcome}` | ингестор | записи `judge:results` по типу и итогу: `stored`, `dropped` (отклонена), `failed`; битые — `type="malformed"` |
| `apparatica_worker_slots{pool}`, `apparatica_worker_busy_slots{pool}` | воркер | все и занятые слоты: `main` — очереди классов ресурсов, `rejudge` — перепроверки |
| `apparatica_worker_queue_wait_seconds{queue}` | воркер | от постановки задания в очередь (время сообщения Dramatiq) до слота; задание, возвращённое в очередь после смерти воркера, считается от первой постановки |
| `apparatica_worker_stage_duration_seconds{stage, status}` | воркер | время этапов, которые запускались, по типу этапа (`lint`, `sim`…) |
| `apparatica_worker_stages_total{stage, status}` | воркер | этапы отчитанных попыток; `status="error"` — внутренняя ошибка этапа |
| `apparatica_worker_attempts_total{outcome}` | воркер | попытки: `done`, `cancelled` или код ошибки, если пайплайн не запустился (`PACKAGE_UNAVAILABLE`, `SANDBOX_UNAVAILABLE`, `ATTEMPTS_EXHAUSTED`) |

Значения очередей ингестор читает из Valkey при каждом опросе. Все экземпляры ингестора отдают одинаковые значения, поэтому дашборд берёт максимум. Метрики этапов и попыток относятся только к проверкам; задания волн занимают слоты и ждут в очереди, но этапы не отчитывают.
