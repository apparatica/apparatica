# 06. Пакет задачи и протокол результатов тестбенча

Пакет задачи — центральный контракт между авторами, CLI судьи, воркерами и платформой. Задачи живут как код в каталоге `problems/` монорепо (на старте; вынос в отдельный репозиторий — изменение CI, а не формата).

## 1. Структура

```
problems/
  tags.yaml                 # справочник тегов: slug, title, sort
  sync-fifo/
    problem.yaml            # манифест, схема — schemas/problem.schema.json
    statement.md            # условие: Markdown + KaTeX + ```wavedrom```; позже statement.<lang>.md
    template.sv             # стартовый код с интерфейсом модуля
    tb/
      tb_top.sv             # верхний модуль тестбенча, подключает apx_tb_pkg
      model.sv              # эталонная поведенческая модель (модуль <top>_model)
      tests.sv              # тест-кейсы, сгруппированные public/hidden
    formal/
      props.sv              # SVA-свойства и checker-модель, подключаются через bind
      props.sby             # шаблон конфига SymbiYosys
    reference/
      sync_fifo.sv          # эталонное решение (может быть несколько)
      sync_fifo.md          # пояснение микроархитектуры
    mutants/
      m01_full_off_by_one.sv
      m02_no_reset_count.sv
    assets/                 # картинки для условия
```

**Отличие от брифа:** вместо раздельных `tb_public.sv` и `tb_hidden.sv` — один верхний модуль с группами тестов. Группа выбирается плюс-аргументом `+apx_groups=public` или `+apx_groups=public,hidden`. Так Run и Submit используют один и тот же скомпилированный бинарник: сборка Verilator — самый дорогой шаг, а бинарник можно кэшировать по ключу `(code_hash, problem_version, toolchain_profile)`. Схема допускает и несколько тестбенчей (`testbenches[]`), если задаче это нужно.

## 2. `problem.yaml`

Полная схема — [schemas/problem.schema.json](schemas/problem.schema.json). Пример:

```yaml
schema: 1
id: sync-fifo
number: 17
version: 3
changelog: "Добавлен тест на одновременные push и pop при полном FIFO"   # что изменилось относительно прошлой версии
leaderboard_epoch: 2          # увеличить, если результаты прошлых версий несравнимы
language: systemverilog
kind: design
title: Синхронный FIFO
difficulty: medium            # ключ из config/difficulties.yaml
tags: [fifo, memory, pointers]
resource_class: light         # light | heavy → имя очереди judge.light / judge.heavy
authors: [{name: "Автор", github: "author"}]
license: CC-BY-SA-4.0

top: sync_fifo
interface:
  parameters:
    - {name: WIDTH, type: int, default: 8}
    - {name: DEPTH, type: int, default: 16}
  ports:
    - {name: clk,   dir: input,  width: "1",     role: clock, description: "Общий тактовый сигнал"}
    - {name: rst_n, dir: input,  width: "1",     role: reset, reset: {active: low, sync: true}, description: "Синхронный сброс, активный 0"}
    - {name: push,  dir: input,  width: "1",     description: "Записать wdata"}
    - {name: wdata, dir: input,  width: "WIDTH", description: "Записываемое слово"}
    - {name: pop,   dir: input,  width: "1",     description: "Удалить слово с вершины"}
    - {name: rdata, dir: output, width: "WIDTH", description: "Слово на вершине очереди"}
    - {name: full,  dir: output, width: "1",     description: "Очередь заполнена"}
    - {name: empty, dir: output, width: "1",     description: "Очередь пуста"}

files:
  statement: statement.md
  template: template.sv

testbenches:
  - id: main
    top: tb_top
    sources: [tb/model.sv, tb/tests.sv, tb/tb_top.sv]
    groups: {public: 12, hidden: 20}   # ожидаемое число тестов, проверяется validate

stages:
  precheck: {type: precheck}
  lint:     {type: lint, flags: ["-Wall"], warnings_fail: false}
  sim_run:  {type: sim, testbench: main, groups: [public], max_cycles: 200000}
  sim_full: {type: sim, testbench: main, groups: [public, hidden], max_cycles: 500000}
  synth:    {type: synth, params: {WIDTH: 8, DEPTH: 16}, clock_period_ns: 2.0, forbid_latches: true}
  netlist_sim: {type: sim, testbench: main, groups: [public, hidden], design: synth.netlist_generic}
  formal:   {type: formal, sources: [formal/props.sv], sby: formal/props.sby, depth: 20}

pipelines:
  practice:
    run:    [precheck, lint, sim_run]
    submit: [precheck, lint, sim_full, synth, netlist_sim, formal]

limits:                        # переопределяют значения класса ресурсов
  stage_timeout_s: {sim_run: 20, sim_full: 40, synth: 60, formal: 120}
  memory_mb: 2048
  output_kb: 1024
  fst_mb: 16

leaderboard:
  formula_version: 1
  order:                       # лексикографически; последняя ступень всегда — время отправки
    - {metric: synth.critical_path_ns, dir: asc}
    - {metric: synth.area_um2, dir: asc}

reference:
  visibility: after_accepted   # after_accepted | public | hidden; по умолчанию — из конфига платформы
  solutions:
    - {file: reference/sync_fifo.sv, title: "Счётчик заполнения", explanation: reference/sync_fifo.md}

mutants:
  - {file: mutants/m01_full_off_by_one.sv, expect: wrong_answer, caught_by: [sim_full], note: "full при DEPTH-1"}
  - {file: mutants/m02_no_reset_count.sv, expect: wrong_answer}
  - {file: mutants/m03_latch.sv, expect: compile_error, caught_by: [synth]}
```

### Правила

- `id` совпадает с именем каталога и становится `slug`. Переименование задачи не поддерживается.
- `version` — целое, растёт на 1. Опубликованную версию нельзя изменить: импорт сравнивает `content_hash` (sha256 по отсортированному списку файлов пакета и их содержимому).
- Ширины портов — выражения от параметров (`"WIDTH"`, `"$clog2(DEPTH)+1"`), вычисляются slang при подстановке значений по умолчанию.
- Роль порта `clock` нужна синтезу (создание клока для STA) и формалу. Комбинационная задача без `clock` получает метрику «задержка вход → выход».
- Набор этапов и порядок задаёт `pipelines`. Ядро не знает типов этапов: оно берёт плагин по `type` из языкового модуля `language`.
- `leaderboard.order` ссылается на метрики как `<stage_key>.<поле>`. Смена порядка или метрик — новый `formula_version`.
- Индустриальный режим (Ф7) — дополнительный ключ `pipelines.industrial` со списком шагов и отдельная формула рейтинга, в которой по умолчанию первым ключом идёт число предупреждений строгого линта (`lint_strict.warnings`, по возрастанию); старые пакеты остаются валидными.
- Задел i18n: `files.statement_i18n: {en: statement.en.md}` и `title_i18n: {en: ...}` разрешены схемой, но не используются.
- `number` (номер в каталоге) обязателен и уникален среди задач; импорт проверяет уникальность.
- `netlist_sim` обязателен в `pipelines.practice.submit` любой задачи с этапом `synth` (проверяет `judge validate`): без него метрики синтеза не попадают в рейтинг (07 §2.5).

## 3. Тестбенч

### 3.1 Требования к тестбенчу

- Пишется на SystemVerilog для Verilator `--binary --timing`.
- Сравнивает выходы решения с эталонной моделью (`<top>_model`) в scoreboard.
- Стимулы: направленные тесты плюс случайные, сид — из `+apx_seed=<N>` (передаётся судьёй; сохраняется в отправке). Рекомендуется генерировать случайные стимулы через `$urandom`/`$urandom_range`. `randomize()` с ограничениями допустим, но Verilator решает ограничения внешним решателем Z3 во время исполнения — это медленнее и требует проверки детерминизма в `judge validate`.
- Не полагается на начальное состояние DUT: судья случайно инициализирует все переменные (07 §2.3), поэтому тестбенч начинает с корректного сброса.
- Учитывает, что Verilator двухзначный: X и Z в симуляции не возникают, проверки «выход не X» бессмысленны.
- Останавливается на первом расхождении в каждом тесте; после первого упавшего теста прогон завершается (оставшиеся помечаются «не запускались») — так быстрее и совпадает с макетом.
- Использует библиотеку `apx_tb_pkg` (поставляется в образе тулчейна), а не пишет протокол вручную.
- Объявляет сигналы `exp_<port>` для всех проверяемых выходов — они попадают в трассу рядом с выходами DUT («ожидаемое vs фактическое» на диаграмме).

### 3.2 Библиотека `apx_tb_pkg`

```systemverilog
import apx_tb_pkg::*;

initial begin
  apx_suite_begin();                                   // читает +apx_seed, +apx_groups, +apx_result
  if (apx_test_begin("t07", "одновременные push и pop", "public")) begin
    // стимулы...
    `APX_CHECK(rdata, exp_rdata)                        // сравнение с записью такта и имени сигнала
    `APX_CHECK_MSG(rdata, exp_rdata,
      "Слово уже записано, но rdata ещё не обновился — посмотрите на диаграмме")  // подсказка для баннера
    apx_test_end();
  end
  apx_suite_end();                                      // пишет итог, вызывает $finish
end
always @(posedge clk) apx_tick();                       // счётчик тактов и границы окна трассы
```

Библиотека отвечает за: чтение плюс-аргументов, фильтрацию групп, счётчик тактов, запись протокола, трассу в окне `+apx_trace_from=<cycle> +apx_trace_to=<cycle>` (`$dumpfile`/`$dumpvars` на такте начала, `$finish` на такте конца — Verilator игнорирует `$dumpoff`; только FST). В режиме окна расхождение не завершает прогон: он идёт до такта конца окна (S5).

### 3.3 Протокол результатов

Два канала:

1. **Файл результатов** (авторитетный) — JSON Lines по пути `+apx_result=<path>`. Код решения не может открыть файл: `$fopen` в решении запрещён статической проверкой. Вердикт строится только по этому файлу.
2. **Строки прогресса в stdout** — `@@apx:<nonce> <json>`, где `nonce` — случайная строка, которую оркестратор передаёт тестбенчу и не раскрывает решению (чтение плюс-аргументов в решении запрещено). Используются только для живого прогресса в UI («тест 4/32 выполняется») и вырезаются из консоли. Строки с неверным `nonce` выводятся как обычный текст.

Схема записи — [schemas/tb-result.schema.json](schemas/tb-result.schema.json). События:

| `event` | Поля | Смысл |
|---|---|---|
| `suite_start` | `seed`, `groups`, `tests_total` | начало прогона |
| `test_start` | `id`, `name`, `group`, `cycle` | начало теста |
| `mismatch` | `test`, `cycle`, `time_ps`, `signal`, `expected`, `actual`, `hint?` | расхождение (может быть несколько сигналов на одном такте); `hint` — подсказка автора задачи для баннера |
| `test_end` | `id`, `status` (`passed`/`failed`), `cycles`, `cycle` | конец теста |
| `suite_end` | `passed`, `failed`, `not_run`, `cycles` | конец прогона |

Значения сигналов — строки в шестнадцатеричном виде с шириной (`"8'h3a"`). Verilator двухзначный, поэтому `x`/`z` в значениях не встречаются.

Если файл результатов не содержит `suite_end` (решение вызвало `$finish`, симуляция упала, таймаут), этап получает `failed` с `failure_kind`, соответствующим причине: таймаут или лимит → `limit`, иначе → `wrong`.

### 3.4 Что видит пользователь

- Открытые тесты (`public`): имя, статус, такт расхождения, таблица «ожидалось / получено», кнопка «показать на диаграмме».
- Скрытые тесты (`hidden`): только счётчик пройденных и номер упавшего; без значений и без трассы.

## 4. Формальные свойства

- Свойства и вспомогательная checker-модель пишутся в `formal/props.sv` и подключаются через `bind <top> <checker> ...`.
- Допустимое подмножество SVA определяется спайком S1 и фиксируется в ADR-0005. Рабочее допущение: immediate `assert`/`assume`/`cover` внутри `always_ff`/`always_comb`, `$past`, `$stable`, `$rose`, `$fell`, вспомогательная логика на синтезируемом SV. Конкурентные `assert property` с `|->`/`|=>` — только если S1 подтвердит поддержку в yosys-slang.
- Имя свойства (метка `p_<name>:`) и описание из комментария `// @desc ...` показываются во вкладке «Формал».

## 5. Мутанты и CLI `judge`

`judge` — CLI того же пакета, что исполняет воркер (одна реализация пайплайна).

| Команда | Что делает |
|---|---|
| `judge validate <path>` | схема `problem.yaml`; все файлы на месте; шаблон парсится и соответствует интерфейсу; эталоны проходят **все** этапы `submit` с несколькими сидами (по умолчанию 3) и дают `accepted`; каждый мутант получает вердикт `expect` и пойман этапом из `caught_by`; число тестов в группах совпадает с `testbenches[].groups`; условие рендерится (KaTeX и WaveDrom без ошибок — проверяется Node-скриптом из фронтенда) |
| `judge run <path> --solution file.sv [--kind run\|submit] [--seed N] [--trace]` | локальный прогон, вывод как в консоли сайта, результаты в `./out` |
| `judge metrics <path>` | синтез эталонов, печать метрик (для README задачи и регрессии) |
| `judge pack <path>` | детерминированный tar.zst пакета и `content_hash` |
| `judge new <slug>` | создать пакет из шаблона |

Локально и в CI `judge` выполняет этапы в контейнере образа тулчейна (`LocalDockerExecutor`); с флагом `--no-docker` — напрямую на хосте (если инструменты установлены). Воркер использует тот же код с `SandboxExecutor`.

## 6. Импорт в платформу

`apparatica-admin problems import <path|git-ref>`:
1. `judge validate` (в CI это уже сделано; импорт повторяет только схему и хэш).
2. Для новой `(slug, version)`: упаковать, загрузить в S3 `packages/<slug>/<version>-<hash>.tar.zst`, создать `problem_versions`, сделать её текущей, если `--publish`.
3. Для существующей `(slug, version)` с тем же хэшем — ничего; с другим — ошибка.
4. Синхронизировать `tags.yaml`.
5. Поставить в очередь прогон эталонов на профиле по умолчанию для заполнения `reference_solutions.metrics` (Ф3).

## 7. Руководство автора

Создаётся в Ф0 как проектная документация `docs/problem-authoring.md` (ссылка из `problems/README.md` и `CONTRIBUTING.md`): структура, шаблон `judge new`, требования к тестбенчу и мутантам (минимум 3 мутанта на задачу, хотя бы один ловится только скрытыми тестами), допустимое SVA, процесс ревью через PR (CI запускает `judge validate` для изменённых пакетов).
