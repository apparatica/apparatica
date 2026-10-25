# Фронтенд

Next.js-приложение в `web/`: как оно устроено, откуда берутся цвета, шрифты и строки, как переключается тема и как тестируются компоненты. Экраны и состояния — [specs/08](../specs/08-screens.md), дизайн — `brief/apparatica-handoff/`.

## Стек

Next.js 16 (App Router), React 19, TypeScript 6 (`strict`), Tailwind CSS 4, next-intl 4, иконки `lucide-react`. Компоненты shadcn/ui добавляются с T1.9; `components.json` уже настроен, `cn()` — в `src/lib/utils.ts`.

```sh
pnpm -C web dev          # http://localhost:3000
pnpm -C web build        # just build-js
pnpm -C web test         # just test-js: Vitest
pnpm -C web typecheck    # just typecheck-js: типы маршрутов Next.js и tsc
```

## Структура

```
web/
  messages/ru.json        все строки интерфейса
  src/app/                маршруты App Router: layout.tsx (тема, шрифты, оболочка), страницы
  src/components/shell/   оболочка: шапка, левая рейка, нижняя навигация, переключатель темы
  src/i18n/               next-intl: request.ts (локаль и сообщения), типы сообщений
  src/lib/api/            типизированный клиент API (docs/api.md)
  src/lib/theme.ts        выбор темы: cookie, скрипт до первой отрисовки
  src/styles/tokens.css   токены дизайна
  src/mocks/              MSW: обработчики и данные по типам API
  src/test/               настройка Vitest и помощники
```

## Токены и тема Tailwind

- **`src/styles/tokens.css`** — копия `brief/apparatica-handoff/design/tokens.css`. Значения меняются только вместе с дизайном.
- **`src/app/globals.css`** переносит `tailwind.theme.ts` из пакета передачи в `@theme` Tailwind 4: цвета (`bg-sf`, `text-mu`, `border-bc`, `bg-acs text-ac` …), шрифты, радиусы, шкала типографики, тени `shadow-window` и `shadow-pop`.
- **Палитра Tailwind по умолчанию удалена** (`--color-*: initial`). Утилиты есть только у токенов, поэтому цвет не из `tokens.css` в классах не сработает.
- **Заголовки — `text-title-1` и `text-title-2`.** В теме передачи они называются `h1` и `h2`, но `text-h1` … `text-h4` уже заняты цветами тепловой карты. Остальные размеры — как в передаче: `text-display`, `text-statement`, `text-body`, `text-caption`, `text-label`, `text-code`, `text-metric`.
- **Имена shadcn/ui** (`bg-primary`, `text-muted-foreground`, `border-input`, `ring` …) сопоставлены токенам по `components.md`. Это те же цвета под другими именами, своих значений у них нет.
- **Отступы** — шкала Tailwind по умолчанию (шаг 4 px). Она совпадает со шкалой передачи.

Тёмная тема — те же переменные под `data-theme="dark"` на `<html>`, поэтому варианты `dark:` не нужны.

## Шрифты

IBM Plex Sans и IBM Plex Mono, начертания 400, 500 и 600, из пакетов `@fontsource/*`. Файлы собираются в приложение, сеть при сборке не нужна. Подмножества (кириллица, латиница и другие) подключены через `unicode-range`, поэтому браузер загружает только нужные. Лицензия — OFL-1.1 (ADR-0012).

## Тема: светлая, тёмная, системная

По умолчанию тема системная. Явный выбор хранится в cookie `ap_theme` (`light`, `dark`, `system`; год, весь сайт).

- **Явный выбор** сервер читает из cookie и рендерит `<html data-theme>` сразу. Страница не мигает и без JavaScript.
- **Системная тема.** Сервер её не знает, поэтому `<html>` приходит без атрибута. Встроенный в `<head>` скрипт (`THEME_SCRIPT`) ставит атрибут по `prefers-color-scheme` до первой отрисовки и следит за сменой темы в ОС.
- **Переключатель** в шапке перебирает системная → светлая → тёмная. Он временный: в T1.9 переедет в меню пользователя и палитру команд (specs/08 §2).

Layout читает cookie, поэтому страницы рендерятся на каждый запрос (динамически).

## Оболочка

Шапка 40 px: знак и «Apparatica», переключатель темы. Левая рейка разделов шириной 48 px. На ширине меньше 640 px вместо неё нижняя навигация, высота целей нажатия от 44 px. Разделы перечислены в `src/components/shell/nav.ts`; «Рейтинг», «Дашборд» и «Профиль» появятся вместе со своими страницами. Хлебные крошки, «Быстрый поиск» (Ctrl+K) и вход появятся вместе с палитрой команд (T1.9) и пользователями (Ф2).

Маршруты сейчас такие: `/` перенаправляет на `/problems`, пока нет дашборда (Ф4); `/problems` — заглушка до каталога (T1.12); остальные адреса ведут на `not-found.tsx`.

## Строки: next-intl

Все строки интерфейса лежат в `web/messages/ru.json`, локаль одна — `ru`, без префикса в адресах. Ключи типизированы (`src/i18n/app-config.d.ts`): `t("shell.nav.problems")` с несуществующим ключом не пройдёт `typecheck`. Серверные компоненты используют `useTranslations` или `getTranslations`, клиентские — `useTranslations` внутри `NextIntlClientProvider` из layout.

## Тесты и моки

- **Vitest** с jsdom и Testing Library, тесты лежат рядом с кодом (`*.test.ts(x)`).
- **Провайдеры.** `renderWithProviders` (`src/test/render.tsx`) оборачивает компонент провайдерами layout.
- **Тема ОС.** `mockColorScheme` (`src/test/match-media.ts`) задаёт тему ОС: в jsdom нет `matchMedia`.
- **Запросы к API** перехватывает MSW (`src/mocks/`). Данные моков типизированы схемой API (`Schemas["ConfigResponse"]` …), поэтому изменение контракта ломает их при компиляции.
- **Запрос без обработчика роняет тест.** Свой обработчик для теста задаётся через `server.use(...)`.
- **Сценарии.** Моки для разработки без бэкенда (в браузере и на сервере Next.js) и сценарии каждой фазы появятся с PR контракта фазы, начиная с T1.0.
