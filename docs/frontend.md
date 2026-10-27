# Фронтенд

Next.js-приложение в `web/`: как оно устроено, откуда берутся цвета, шрифты и строки, как переключается тема, какие есть компоненты и как они тестируются. Экраны и состояния — [specs/08](../specs/08-screens.md), дизайн — `brief/apparatica-handoff/`.

## Стек

Next.js 16 (App Router), React 19, TypeScript 6 (`strict`), Tailwind CSS 4, next-intl 4, TanStack Query 5, иконки `lucide-react`. Базовые контролы — по образцу shadcn/ui на Radix UI (пакет `radix-ui`), палитра команд — `cmdk`, уведомления — `sonner`, варианты классов — `class-variance-authority`; `cn()` — в `src/lib/utils.ts`. Истории компонентов — Storybook 10 (`@storybook/nextjs-vite`).

```sh
pnpm -C web dev          # http://localhost:3000
pnpm -C web build        # just build-js
pnpm -C web test         # just test-js: Vitest
pnpm -C web typecheck    # just typecheck-js: типы маршрутов Next.js и tsc
pnpm -C web storybook    # just storybook: http://localhost:6006
```

## Структура

```
web/
  messages/ru.json        все строки интерфейса
  .storybook/             Storybook: main.ts (фреймворк, истории), preview.tsx (стили, тема, next-intl)
  src/app/                маршруты App Router: layout.tsx (тема, шрифты, оболочка), страницы
  src/components/shell/   оболочка: шапка, левая рейка, нижняя навигация, меню гостя, палитра команд
  src/components/ui/      базовые контролы листа CmpD (ниже)
  src/components/domain/  доменные компоненты листа CmpA: вердикт, конвейер, сложность, теги
  src/features/submission/  проверка на странице задачи: useSubmission, машина состояний, поток событий
  src/i18n/               next-intl: request.ts (локаль и сообщения), типы сообщений
  src/lib/api/            типизированный клиент API (docs/api.md); browser.ts — клиент браузера
  src/lib/query.tsx       TanStack Query: QueryClient для данных, которые браузер берёт из API
  src/lib/config.ts       useConfig(): GET /config в браузере (уровни сложности, флаги, лимиты)
  src/lib/theme.ts        выбор темы: cookie, скрипт до первой отрисовки
  src/lib/shortcuts.ts    сочетания клавиш: Ctrl или ⌘, aria-keyshortcuts, сравнение с keydown
  src/styles/tokens.css   токены дизайна
  src/mocks/              MSW: обработчики, данные по типам API, записанные сценарии проверок
  src/instrumentation.ts  моки на сервере Next.js в режиме разработки без бэкенда
  public/mockServiceWorker.js  service worker MSW (создаёт msw init)
  src/test/               настройка Vitest и помощники
```

## Токены и тема Tailwind

- **`src/styles/tokens.css`** — копия `brief/apparatica-handoff/design/tokens.css`. Значения меняются только вместе с дизайном.
- **`src/app/globals.css`** переносит `tailwind.theme.ts` из пакета передачи в `@theme` Tailwind 4: цвета (`bg-sf`, `text-mu`, `border-bc`, `bg-acs text-ac` …), шрифты, радиусы, шкала типографики, тени `shadow-window` и `shadow-pop`.
- **Палитра Tailwind по умолчанию удалена** (`--color-*: initial`). Утилиты есть только у токенов, поэтому цвет не из `tokens.css` в классах не сработает.
- **Заголовки — `text-title-1` и `text-title-2`.** В теме передачи они называются `h1` и `h2`, но `text-h1` … `text-h4` уже заняты цветами тепловой карты. Остальные размеры — как в передаче: `text-display`, `text-statement`, `text-body`, `text-caption`, `text-label`, `text-code`, `text-metric`.
- **Имена shadcn/ui** (`bg-primary`, `text-muted-foreground`, `border-input`, `ring` …) сопоставлены токенам по `components.md`. Это те же цвета под другими именами, своих значений у них нет.
- **Отступы** — шкала Tailwind по умолчанию (шаг 4 px). Она совпадает со шкалой передачи.
- **`cn()` знает шкалу типографики.** Без этого `tailwind-merge` принял бы `text-caption` за цвет и в `cn("text-caption text-mu")` выбросил бы размер.
- **`--shim`** — блик скелетона. Его нет в `tokens.css`: значение взято из исходников макетов (`source/*.dc.html`) и задано в `globals.css` для обеих тем, как и анимация `animate-shim`.
- **Контур фокуса** задаёт `tokens.css` (`:focus-visible`, 2 px `--ac` со смещением 2 px). Это правило вне слоёв Tailwind и перебивает утилиты, поэтому изменить его у отдельного элемента можно только утилитой с `!` (`outline-none!`, `focus-visible:-outline-offset-2!`).

Тёмная тема — те же переменные под `data-theme="dark"` на `<html>`, поэтому варианты `dark:` не нужны.

## Шрифты

IBM Plex Sans и IBM Plex Mono, начертания 400, 500 и 600, из пакетов `@fontsource/*`. Файлы собираются в приложение, сеть при сборке не нужна. Подмножества (кириллица, латиница и другие) подключены через `unicode-range`, поэтому браузер загружает только нужные. Лицензия — OFL-1.1 (ADR-0012).

## Тема: светлая, тёмная, системная

По умолчанию тема системная. Явный выбор хранится в cookie `ap_theme` (`light`, `dark`, `system`; год, весь сайт).

- **Явный выбор** сервер читает из cookie и рендерит `<html data-theme>` сразу. Страница не мигает и без JavaScript.
- **Системная тема.** Сервер её не знает, поэтому `<html>` приходит без атрибута. Встроенный в `<head>` скрипт (`THEME_SCRIPT`) ставит атрибут по `prefers-color-scheme` до первой отрисовки и следит за сменой темы в ОС.
- **Выбор** — в меню гостя («Гость» в шапке; с аккаунтами — меню пользователя) и в палитре команд (specs/08 §2). Оба меняют тему через общий контекст `ThemeProvider` (`src/components/shell/theme.tsx`).

Layout читает cookie, поэтому страницы рендерятся на каждый запрос (динамически).

## Оболочка

Шапка 40 px: знак и «Apparatica», «Быстрый поиск» с подсказкой Ctrl K (на телефоне — только значок), чип «Гость» с меню темы. Левая рейка разделов шириной 48 px. На ширине меньше 640 px вместо неё нижняя навигация, высота целей нажатия от 44 px. Разделы перечислены в `src/components/shell/nav.ts`; «Рейтинг», «Дашборд» и «Профиль» появятся вместе со своими страницами. Хлебные крошки появятся со страницей задачи (T1.13), вход — с пользователями (Ф2).

**Палитра команд** (`command-palette.tsx`) открывается по Ctrl+K (⌘K на Mac) или кнопкой «Быстрый поиск», закрывается по Esc или тому же сочетанию. Группа «Задачи» — до 8 задач из `GET /problems?q=` (поиск в названии и тегах), пока строка не пуста, справа — компактный `DifficultyBadge` уровня из `GET /config`; группа «Действия» — «Перейти к задачам» и выбор темы, фильтруется по вводу. Стрелки выбирают пункт, Enter выполняет.

## Базовые контролы

`src/components/ui/` — контролы листа CmpD (`components.md`) по образцу shadcn/ui: код в репозитории, примитивы Radix, классы только из токенов. Высота обычных элементов 30 px, на сенсорных экранах (`pointer-coarse`) — 44 px.

| Файл | Что | Состояния |
|---|---|---|
| `button.tsx` | `Button` | `primary`, `default`, `ghost`, `selected`; `size="icon"`; `disabled` (45%); `loading` — значок `loader-circle` и кнопка недоступна; `asChild` — ссылка в виде кнопки |
| `kbd.tsx` | `Kbd`, `Shortcut`, `useApple` | подсказка клавиш mono 10.5 px; `Shortcut keys={["Mod","Enter"]}` пишет «Ctrl ↵» или «⌘ ↵». Сервер и первая отрисовка всегда пишут Ctrl, чтобы гидратация совпала |
| `input.tsx` | `Input`, `Field`, `SearchInput` | обычное, фокус, ошибка (`Field error` — граница `--er`, сообщение с `circle-x`, `aria-invalid`), недоступно; `Field` связывает подпись, подсказку и ошибку с полем через render-prop |
| `checkbox.tsx`, `radio-group.tsx`, `switch.tsx` | флажок, переключатель, тумблер 30 × 16 | выключен, включён, фокус, недоступно |
| `tabs.tsx` | `Tabs`, `TabsList variant`, `TabsTrigger` | `line` — линия 2 px под активной; `segmented` — переключатель периода |
| `dropdown-menu.tsx` | меню | пункты 28 px, подсвеченный `--acs`, сочетание справа, радиогруппа с галочкой |
| `tooltip.tsx` | `Tooltip`, `TooltipProvider` | через 300 мс, фон `--tx`, до 210 px; провайдер в layout |
| `toast.tsx` | `notify`, `Toaster` | `ok`, `wn`, `er`, `in`: полоса 3 px слева, значок, заголовок, подпись, «Закрыть»; `Toaster` в layout, внизу справа |
| `pagination.tsx` | `Pagination`, `pageItems` | страницы-ссылки, текущая `--acs` с границей `--ac`, «…», недоступные стрелки на краях |
| `avatar.tsx` | `Avatar` | 20, 28, 40 px, инициалы (одна буква в малых) или картинка |
| `skeleton.tsx` | `Skeleton` | блик `--shim`; при `prefers-reduced-motion` без анимации |
| `dialog.tsx` | `Dialog` и части | окно `shadow-window` без затемнения страницы (макеты ModalsA/B), шапка, тело, подвал на `--sf2`, «Закрыть» |
| `command.tsx` | `Command` и части (`cmdk`) | строка поиска 38 px с «Esc», группы с подписями, пункты 30 px, выбранный `--acs` |

У каждого состояния есть компонентный тест (`*.test.tsx` рядом).

## Доменные компоненты

`src/components/domain/` — компоненты листа CmpA (`components.md`). Каждое состояние — история в Storybook (`*.stories.tsx` рядом) и тест на неё (specs/08 §4). Статус нигде не передаётся одним цветом: у каждого свой значок и текст.

| Файл | Что | Состояния |
|---|---|---|
| `verdict-badge.tsx` | `VerdictBadge status` | 10 статусов отправки (`Submission.status`); `queued` с `position` — «В очереди · позиция 3», `running` со `stage` и `elapsedMs` — «Выполняется · синтез 4,2 с» и вращающийся значок; `internal_error` — контур 1,5 px без заливки; `compact` — квадрат 26 × 26 только со значком, текст в `title` и `aria-label` |
| `pipeline.tsx` | `PipelineStage`, `Pipeline` | 8 статусов этапа (`StageResult.status`): ожидает, идёт, чисто, предупреждение, ошибка, пропущен (пунктир и штриховка), отменён, сбой платформы (рамка без заливки). Подпись — «‹статус или `detail`› · ‹время›»; если `detail` заменяет слово статуса, слово остаётся для скринридеров |
| `difficulty-badge.tsx` | `DifficultyBadge`, `findDifficulty` | уровни из `GET /config` (`config/difficulties.yaml`): цвет по `token`, столбиков закрашено по месту уровня в списке (не больше трёх); `compact` — 18 px без столбиков (палитра команд) |
| `tag-chip.tsx` | `TagChip` | обычный, `selected` (акцент), `removable` (выбран и со значком `x`, «сбросить» для скринридеров); `asChild` — вид чипа у ссылки или кнопки |

**Конвейер** — четыре блока: `lint`, `sim`, `synth`, `formal` (`PIPELINE_BLOCKS`). `precheck` показывается в блоке «Линт», `netlist_sim` — в блоке «Синтез» (specs/08 §6); этапы проверки на блоки раскладывает панель результатов. Ширина блока — ширина его текста плюс доля свободного места по времени этапа (`stageGrow`): у незапущенных доли нет, без времён место делится поровну.

**Storybook.** `just storybook` открывает истории на http://localhost:6006, тема переключается на панели инструментов (`data-theme` на `<html>`, как в layout). Декораторы `.storybook/preview.tsx` — стили приложения, шрифты, тема и `NextIntlClientProvider` с `messages/ru.json`. CI собирает статический Storybook (`just build-storybook`), поэтому сломанная история или конфигурация роняет сборку.

**Тесты по историям.** Тест рендерит историю через `composeStories` из `@storybook/react`; `src/test/setup.ts` подключает декораторы Storybook (`setProjectAnnotations`), поэтому истории в тестах получают те же провайдеры. `@storybook/nextjs-vite` в Vitest без своего Vite-плагина не работает, а доменным компонентам API Next.js не нужны.

Маршруты сейчас такие: `/` перенаправляет на `/problems`, пока нет дашборда (Ф4); `/problems` — заглушка до каталога (T1.12); остальные адреса ведут на `not-found.tsx`.

## Строки: next-intl

Все строки интерфейса лежат в `web/messages/ru.json`, локаль одна — `ru`, без префикса в адресах. Ключи типизированы (`src/i18n/app-config.d.ts`): `t("shell.nav.problems")` с несуществующим ключом не пройдёт `typecheck`. Серверные компоненты используют `useTranslations` или `getTranslations`, клиентские — `useTranslations` внутри `NextIntlClientProvider` из layout.

## Проверка: `useSubmission`

Хук страницы задачи (`src/features/submission/`): Run и Submit создают отправку, поток её событий ([api.md](api.md#события-проверки)) ведёт состояние панели результатов. Компоненты панели появятся в T1.15a–T1.17 и берут данные только из хука.

```ts
const s = useSubmission({ problem: "sync-fifo", version: 1 });
s.start({ kind: "run", code });   // s.starting === "run", пока API создаёт отправку
s.check;                          // живое состояние проверки, null до первой
s.cancel(); s.reconnect();
```

Что отдаёт хук:

| Поле | Что это |
|---|---|
| `check` | состояние проверки, которое собрано из событий потока (`machine.ts`): `status`, `queue` (позиция и ожидание), `attempt`, `stages` (как `StageResult`, начатый этап — `running` до `stage_end`, тесты заменяются по `id`), `heartbeat` молчаливого шага, `console`, `done`, `verdict` |
| `submission` | отправка из `GET /submissions/{id}`: как создана или восстановлена, после `finalized` перечитывается (артефакты, FST) |
| `connection` | поток: `connecting`, `open`, `waiting` (номер переподключения и его время), `failed`, `closed` (после `finalized`) |
| `quota` | остаток квот из ответа `POST` или `GET /submissions` |
| `restoring`, `starting`, `cancelling` | идёт поиск последней отправки, создание (`run` или `submit`), отмена |
| `error` | ошибка последнего `start` или `cancel`: `problem+json` (`RATE_LIMITED`, `CAPTCHA_REQUIRED` …) или сетевая. Текущая проверка при этом остаётся |

**Машина состояний.** `status` — `queued`, затем `running` с первым `stage_start`, затем статус из `finalized`; итог берётся только из него. Событие воркера с номером попытки больше текущего сбрасывает этапы, тесты и консоль: проверка началась заново. События с ID не больше последнего применённого пропускаются, поэтому повтор после переподключения ничего не дублирует. Если `finalized` пришёл, пока этап шёл (отмена, сбой), этап становится `cancelled` или `error`. Консоль — строки этапов, отметка `truncated` и отметка «соединение потеряно» со временем (FR-CON-05).

**Поток событий** читается через `fetch`, а не `EventSource` (`sse.ts`, `stream.ts`): нужны свои задержки переподключения и `Last-Event-ID` после последнего применённого события, и в jsdom нет `EventSource`. Обрыв потока без `finalized` или сетевая ошибка — переподключение через 1, 2, 4, 8, 15 с (specs/07 §4.2); любое пришедшее событие сбрасывает счётчик. После пятой неудачи поток ждёт `reconnect()` («Подключиться сейчас»), он же переподключает сразу во время ожидания. Отметка в консоли ставится один раз на обрыв, а не на каждую попытку. `404` — отправки больше нет: `failed` с ошибкой, без переподключений.

**Восстановление** (FR-RUN-06). При открытии страницы хук берёт последнюю отправку задачи (`GET /submissions?problem=…&limit=1`, затем `GET /submissions/{id}`) и читает её поток с начала. У незавершённой проверки так дочитываются события, у завершённой API отдаёт консоль из архива; без журнала остаются этапы из базы. Если пользователь успел запустить новую проверку, восстановление её не заменяет.

**Новая проверка** заменяет предыдущую: поток старой закрывается, её события больше не применяются. Хук держит проверку только открытой задачи (`problem`): при переходе на другую задачу состояние сбрасывается и ищется её последняя отправка. Живое состояние хранится во внешнем хранилище (`store.ts`, `useSyncExternalStore`): события меняют его без `setState` в эффектах. Запросы к API идут через TanStack Query, `QueryProvider` подключён в layout.

## Тесты и моки

- **Vitest** с jsdom и Testing Library, тесты лежат рядом с кодом (`*.test.ts(x)`).
- **Провайдеры.** `renderWithProviders` (`src/test/render.tsx`) оборачивает компонент провайдерами layout, `Providers` — то же для `renderHook`. У каждого теста свой `QueryClient` без повторов запросов.
- **Тема ОС.** `mockColorScheme` (`src/test/match-media.ts`) задаёт тему ОС: в jsdom нет `matchMedia`.
- **Radix и cmdk в jsdom.** `src/test/dom.ts` добавляет то, чего в jsdom нет: `ResizeObserver`, `scrollIntoView`, захват указателя.
- **Запросы к API** перехватывает MSW (`src/mocks/`). Данные моков типизированы схемой API (`Schemas["ConfigResponse"]` …), поэтому изменение контракта ломает их при компиляции.
- **Запрос без обработчика роняет тест.** Свой обработчик для теста задаётся через `server.use(...)`.
- **Состояние моков** (созданные отправки) сбрасывается после каждого теста. `configureMocks({ speed: Infinity })` завершает проверки мгновенно; `eventsHandler({ dropAfter: N })` обрывает поток событий после N событий.

## Моки для разработки

Обработчики MSW из `src/mocks/handlers.ts` работают и в тестах, и вместо бэкенда при разработке:

```sh
just dev-mocks    # http://localhost:3000; то же, что NEXT_PUBLIC_API_MOCKING=enabled pnpm -C web dev
```

С флагом `NEXT_PUBLIC_API_MOCKING=enabled` запросы браузера к API перехватывает service worker (`public/mockServiceWorker.js`), а запросы сервера Next.js — `src/instrumentation.ts`. Содержимое страницы гидратируется после старта worker'а, поэтому и первые запросы получают моки. Запросы без обработчика уходят в сеть. У браузера и сервера состояние моков своё. Новые обработчики добавляет PR контракта каждой фазы (specs/05 §0).

**Каталог.** `GET /problems` (`src/mocks/problems.ts`) отдаёт пять демо-задач из `problems/` (`fixtures.problems`) с фильтрами API: поиск `q` в названии и slug тегов, `difficulty`, `tag`, страницы.

**Проверки.** Отправка в моках воспроизводит записанный сценарий: события потока с настоящими задержками, а `GET /submissions/{id}` показывает состояние на текущий момент. Сценарий выбирается меткой в коде решения, например `// mock: wrong-answer`. Без метки Run воспроизводит `run-passed`, а Submit — `accepted`. Задача и версия отправки — из запроса, остальное — из записи.

| Сценарий | Что показывает |
|---|---|
| `run-passed`, `accepted` | Run и Submit приняты |
| `accepted-with-warnings` | Submit принят с замечанием линта |
| `wrong-answer` | Run упал на открытом тесте; есть FST-трасса окна ошибки |
| `wrong-answer-hidden` | Submit упал на скрытом тесте |
| `compile-error`, `forbidden-construct` | precheck: ошибка компиляции, запрещённая конструкция |
| `output-limit` | превышен лимит вывода (`truncated`; в записи лимит снижен до 16 КБ, чтобы файл был небольшим) |
| `cancelled` | проверка отменена во время симуляции |
| `internal-error` | сбой платформы на этапе (`EXECUTOR_FAILED`) |
| `retry` | воркер первой попытки пропал, проверка прошла со второй (`attempt: 2`) |

Кнопка «Отменить» в моках работает в любом сценарии: поток доходит до момента отмены и заканчивается `finalized` со статусом `cancelled`. Квота гостя из фикстуры конфига (10 проверок в час) расходуется созданными отправками; на одиннадцатой мок отвечает `429 RATE_LIMITED`.

**Запись сценариев.** Сценарии в `src/mocks/scenarios/*.json` не пишутся вручную. Их записывает `just record-scenarios` (`scripts/record_scenarios.py`): он проверяет решения демо-задач в образе тулчейна и добавляет к событиям пайплайна то, что добавят воркер, API и ингестор (specs/07 §4.1). Это `attempt`, склейка строк лога, heartbeat на молчаливых шагах, `queue` до прогона и `finalized` после. Тест бэкенда `test_mock_scenarios.py` сверяет файлы со схемами API. Поэтому при изменении событий или отправки нужно перезаписать сценарии: `just record-scenarios` или `just record-scenarios wrong-answer`. ID событий в файле задают время воспроизведения; `queue` мок отдаёт без `id:`, как API ([api.md](api.md#события-проверки)).
