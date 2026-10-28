# Просмотрщик волн (`waveview`)

Временные диаграммы показывает Surfer — web-сборка (WASM) на отдельном origin, встроенная в страницу задачи изолированным iframe (ADR-0004, отчёт [S3](spikes/s3.md)). Каталог [`waveview/`](../waveview) собирает этот сайт: Surfer закреплённой версии с двумя темами Apparatica и своя страница с адаптером `postMessage`. Вкладку волн страницы задачи и клиент адаптера (`web/src/features/waveview/`) описывает [frontend.md](frontend.md#страница-задачи).

## Состав

| Путь | Что это |
|---|---|
| `waveview/versions.lock` | `WAVEVIEW_VERSION` — версия сайта; тег и коммит Surfer; trunk, wasm-bindgen и binaryen с sha256 |
| `waveview/Dockerfile` | сборка: Surfer из исходников с нашими темами, затем сайт в `/srv/waveview/<версия>/` образа на busybox |
| `waveview/themes/` | темы `apparatica-light` и `apparatica-dark`: палитра `tokens.css` (фон `--ed`, линии `--tx`, такт `--ac`, шины `--in`, курсор `--er`) и цвета `Clock`, `Bus`, `Expected`, `Error` для сигналов |
| `waveview/site/` | своя страница `index.html` (без аналитики, service worker и встроенных скриптов), `adapter.js`, `waveview.css`, `SOURCE.txt` |
| `waveview/tests/` | проверки без сборки (темы и палитра, версия на стенде) и регрессия сборки в браузере |

В сайт версии попадают `index.html`, `adapter.js`, `waveview.css`, `surfer.js` и `surfer_bg.wasm` (13 МБ, 3 МБ в brotli), лицензия EUPL-1.2 и `SOURCE.txt` со ссылками на исходники.

**Изменение Surfer.** Web-Surfer выбирает тему только по имени из встроенного списка, поэтому сборка добавляет две наши темы в `themes/` исходников и в список `libsurfer/src/config.rs` (одна строка `sed` на тему в Dockerfile). Других изменений нет. Surfer — EUPL-1.2: изменения лежат в этом репозитории, страница ссылается на лицензию и исходники (ADR-0012).

**Версия.** `WAVEVIEW_VERSION` поднимается при любом изменении сборки (Dockerfile, `versions.lock`, темы, страница, адаптер). Она задаёт неизменяемый тег образа и путь в бакете; браузер кэширует версию навсегда. Профиль тулчейна называет версию своего просмотрщика (`apparatica-admin toolchain add … --waveview <версия>`, [development.md](development.md#профили-тулчейна)): формат FST, который пишет Verilator, и Surfer обновляются вместе. API отдаёт адрес просмотрщика в отправке: `waveview_url` = `APX_WAVEVIEW_URL/<версия профиля>/index.html` ([api.md](api.md)).

## Адаптер

`adapter.js` — свой протокол на `postMessage`, версия 1. Он опирается на WCP Surfer (версионированный, отвечает на каждую команду, сообщает о загрузке). Нестабильные сообщения `Message` нужны только там, где у WCP команды нет: загрузка байтов (`LoadFromData`), тема (`SelectTheme`), панели (`Set*Visible`), отображаемые имена (`ItemNameChange`), порядок (`Batch`). Их проверяет регрессия при каждой сборке.

Сообщения родителя — `{apx: 1, id, type, …}`; ответ несёт тот же `id`:

| `type` | Поля | Ответ |
|---|---|---|
| `load` | `bytes` (ArrayBuffer, лучше передать), `timeoutMs` (5000) | `loaded` `{ms}` |
| `signals` | `items: [{path, color?, label?}]` — полное имя, цвет темы, отображаемое имя | `ack` `{added}`: какие сигналы нашлись в FST |
| `cursor`, `center` | `time` | `ack` |
| `marker` | `time`, `name` | `ack` |
| `range` | `from`, `to` | `ack` |
| `fit` | — | `ack` |
| `theme` | `name`: `apparatica-light` или `apparatica-dark` | `ack` |
| `chrome` | `menu`, `toolbar`, `side`, `overview`, `status` (по умолчанию все `false`) | `ack` |

Время — в единицах FST (пикосекунды, `cursor_time_ps` из API). Ошибка команды — `error` `{id, message}`. Без запроса приходят `ready` `{protocol, commands}` (Surfer готов), `crashed` `{message}` (паника Surfer: просмотрщик мёртв, iframe пересоздаётся) и `error` `{message}` (необработанная ошибка).

Чего Surfer не сообщает и что адаптер делает сам:

- **Ошибка разбора FST** видна только в журнале Surfer, а на экране остаётся прошлый файл. `load` ждёт события `waveforms_loaded` не дольше `timeoutMs` и отвечает ошибкой; после неё iframe нужно пересоздать.
- **Неизвестный сигнал** Surfer молча пропускает. Поэтому `signals` добавляет сигналы по одному и возвращает найденные.

Адаптер принимает сообщения только от `window.parent` и отвечает с `targetOrigin "*"`: у iframe origin `null`, а встраивать сайт может только страница из `frame-ancestors` CSP.

Surfer работает на кадрах анимации (eframe): браузер не рисует iframe чужого origin, скрытый через `display: none` или `visibility: hidden`, и такой просмотрщик не запускается и не отвечает. Страница прячет его под непрозрачным слоем, а не средствами CSS.

## Origin и заголовки

Сайт — бакет `waveview`, отданный Garage как website, за своим поддоменом (на стенде `http://waveview.web.localhost:8080`, `deploy/Caddyfile`). iframe страницы задачи — `sandbox="allow-scripts"` без `allow-same-origin`: код внутри не достаёт до cookie, DOM и сети сайта (проверено в S3 и регрессией). Заголовки origin:

| Заголовок | Значение и зачем |
|---|---|
| `Content-Security-Policy` | `default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; frame-ancestors <сайт>` (NFR-SEC-07) |
| `Access-Control-Allow-Origin: *` | у iframe origin `null`: модуль и WASM он запрашивает в режиме CORS |
| ответ `204` на `OPTIONS` | антивирусы добавляют к `fetch` заголовки, и обычный GET становится preflight |
| `Cache-Control: public, max-age=31536000, immutable` | для путей версий: версия не меняется |
| `Content-Type` | хранится при загрузке: `application/wasm` для WASM |

Caddy сжимает ответы (`encode zstd gzip`). Production-заголовки и TLS — T1.23.

## Сборка и публикация

```sh
just waveview-build   # образ apparatica-waveview:dev и файлы в waveview/dist (6–10 минут)
just waveview-test    # регрессия: сборка в браузере через адаптер
just waveview-serve   # сборка на http://localhost:3901 для страницы задачи в just dev-mocks
```

Сборке нужны Docker Hub (образ Rust), gitlab.com (исходники Surfer), github.com (trunk и инструменты), crates.io. На медленной сети — `WAVEVIEW_RUST_IMAGE=mirror.gcr.io/library/rust:1.95-trixie@sha256:<digest из Dockerfile>` (и `WAVEVIEW_RUNTIME_IMAGE` для busybox).

**CI** (`.github/workflows/waveview.yml`) собирает образ при изменении `waveview/`, прогоняет проверки и регрессию в Chrome раннера и при новом `WAVEVIEW_VERSION` публикует `ghcr.io/<owner>/waveview:<версия>` (и `sha-<коммит>`). Опубликованный тег не перезаписывается: изменение сборки без новой версии не проходит CI. Образ в GHCR должен быть публичным, чтобы стенд скачивал его без входа.

**Стенд.** Одноразовый сервис `waveview` копирует `/srv/waveview/` из образа (`WAVEVIEW_IMAGE`, по умолчанию `ghcr.io/apparatica/waveview:<версия>`) в том, `garage-setup` загружает в бакет версии, которых там нет (`index.html` — последним). Локальная сборка: `WAVEVIEW_IMAGE=apparatica-waveview:dev` в `deploy/.env`. `just stand-check` проверяет, что версия отдаётся с нужными заголовками.

## Регрессия

`waveview/tests/regression.test.mjs` (`just waveview-test`, `WAVEVIEW_DIST` — каталог сборки, по умолчанию `waveview/dist`) поднимает два origin с заголовками стенда (`tests/serve.mjs`) и через `playwright-core` открывает в браузере (`WAVEVIEW_BROWSER`: `chrome`, на Windows можно `msedge`) родительскую страницу с изолированным iframe:

1. Просмотрщик готов, у iframe origin `null`, родитель, cookie, хранилище и сеть сайта недоступны.
2. FST сценария мока `wrong-answer` (записан текущим профилем тулчейна) загружается; все сигналы из `waveform.signals` находятся в FST; курсор, метка, зум, панели работают.
3. Обе темы применяются: фон диаграммы — `--ed` своей темы. Чужая тема — ошибка.
4. Испорченный файл даёт ошибку или `crashed`, страница работает, новый iframe снова открывает FST.

`WAVEVIEW_SCREENSHOTS=<каталог>` сохраняет снимки обеих тем.

Не проверено: Firefox и Safari (нужен WebGL2), экранные дикторы (`accesskit` включён в сборку).
