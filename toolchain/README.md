# Образ тулчейна

Образ, в котором песочница выполняет все этапы проверки (ADR-0003, specs/07 §5). Один опубликованный образ — один профиль тулчейна (`ToolchainProfile`): результаты сравнимы только в пределах профиля.

Сейчас собран профиль 1: Verilator, Z3, pyslang, Verible, `apx-run`, `apx-verilate`, библиотека тестбенча `apx_tb_pkg`. Yosys, OpenSTA и liberty Nangate45 добавятся в T3.1a, SymbiYosys — в T5.1.

## Состав

| Что | Где | Откуда |
|---|---|---|
| Verilator | `/opt/verilator` | исходники с GitHub по тегу, sha256 в `versions.lock` |
| Рантайм Verilator, предсобранный | `/opt/apx/verilator-runtime/libverilated_apx.a` | собирается при сборке образа (`apx-verilate/build-runtime.sh`) |
| Verible | `/opt/verible` | статическая сборка с GitHub, sha256 в `versions.lock` |
| pyslang | `/opt/apx/venv` (первый в `PATH` Python) | колесо PyPI по хэшу |
| Z3, g++, make, Python 3.13 | пакеты Debian trixie | версии проверяют тесты образа |
| `apx-run`, `apx-verilate` | `/opt/apx/bin` | этот каталог |
| `apx_tb_pkg.sv` | `/opt/apx/sv` | `sv/` |
| Лицензии Verilator и Verible | `/opt/licenses` | из исходников; лицензии пакетов Debian — в `/usr/share/doc/*/copyright` |

Команды выполняются от непривилегированного пользователя `sandbox` (UID 10001), рабочий каталог и `HOME` — `/work`. В песочнице корневая ФС только для чтения, `/work` — tmpfs.

## `apx-run`

Под `docker exec -t` stderr сливается со stdout. `apx-run COMMAND [ARGS...]` даёт команде отдельные псевдотерминалы для stdout и stderr — инструменты видят TTY и выводят построчно — и пишет оба потока в свой stdout:

- строки stdout — как есть;
- строки stderr — с байтом `0x1E` (ASCII record separator) в начале; оркестратор снимает его и назначает канал `err`;
- строки разных потоков не склеиваются; без перевода строки хвост выводится после 50 мс тишины;
- код выхода — код команды, `128+N` при гибели от сигнала N, `127`, если команду не удалось запустить;
- после выхода команды `apx-run` ждёт вывод оставшихся процессов не дольше 200 мс; убивает их оркестратор (specs/07 §5.2).

Метка канала косметическая: вердикт от неё не зависит, подделка из `$display` меняет только цвет строки.

## `apx-verilate`

`apx-verilate [АРГУМЕНТЫ VERILATOR...]` — Verilator с флагами `--binary --timing --trace-fst`, для которых собран рантайм в образе. Рантайм не компилируется на каждую отправку: `make` получает пустые `VM_GLOBAL_FAST`/`VM_GLOBAL_SLOW`, а объекты берутся из `libverilated_apx.a`. Остальные флаги (`--x-assign`, `--x-initial`, `-Wno-*`, `-j`, исходники, `--top-module`) передаёт этап `sim` (specs/07 §2.3).

Флаги, влияющие на рантайм, менять только здесь: библиотека совпадает с ними. При сборке образа `build-runtime.sh` компилирует эталонный тестбенч `runtime_ref.sv` со всеми нужными частями рантайма (timing, FST, рандомизация, потоки) и падает, если набор объектов изменился.

## `apx_tb_pkg`

Библиотека тестбенчей задач (specs/06 §3.2): плюс-аргументы, группы, счётчик тактов, протокол результатов в файл JSON Lines и строки прогресса `@@apx:<nonce>` в stdout, лимит тактов, окно трассы FST. Этап `sim` компилирует `/opt/apx/sv/apx_tb_pkg.sv` первым, с `--timescale 1ps/1ps` (specs/07 §2.3). Разбор протокола на стороне судьи — `judge/src/judge/languages/systemverilog/tbproto.py`; тесты образа `tests/test_apx_tb_pkg.py` собирают тестбенч с библиотекой и разбирают результат этим модулем.

Правка библиотеки — изменение образа: новый `TOOLCHAIN_PROFILE`. Задачи, собранные со старым профилем, продолжают работать со старой версией библиотеки.

## Версии и профиль

`versions.lock` — строки `KEY=value`: версии и sha256 загружаемых инструментов, ожидаемые версии пакетов Debian и `TOOLCHAIN_PROFILE`. Dockerfile читает его при сборке, тесты образа сверяют с ним установленные версии.

Пакеты Debian ставятся из текущего trixie поверх базового образа, закреплённого по digest. Если при пересборке apt поставит более новую версию, тесты образа упадут: обновите `versions.lock`. Профиль закрепляет опубликованный образ (его digest), а не возможность пересобрать его побайтно.

Как обновить инструмент:

1. Поменяйте версию и sha256 в `versions.lock`, увеличьте `TOOLCHAIN_PROFILE`. Профиль увеличивается при любом изменении образа, включая `apx-run`, `apx-verilate` и `apx_tb_pkg`.
2. `just toolchain-build && just toolchain-test`.
3. После слияния в `master` CI публикует образ. Перевод задач на новый профиль — specs/09 §2.

## Сборка и тесты

```sh
just toolchain-build   # docker build → apparatica-toolchain:dev
just toolchain-test    # тесты образа: pytest на хосте, команды в контейнере песочницы
```

Если Docker Hub или `deb.debian.org` недоступны, задайте зеркала через переменные окружения:

```sh
TOOLCHAIN_BASE_IMAGE=mirror.gcr.io/library/debian@sha256:<digest из Dockerfile>
TOOLCHAIN_DEBIAN_MIRROR=http://mirror.yandex.ru/debian
```

Тесты образа (`tests/`) запускаются pytest на хосте из окружения `judge` (нужен Docker). Фикстура поднимает один контейнер с ограничениями песочницы specs/07 §5.1 (`tests/sandbox.py`) и выполняет каждую команду через `docker exec` — так же, как оркестратор выполняет этапы; инструменты тестирования в образ не попадают. Тесты проверяют версии, ограничения песочницы, сборку и симуляцию с FST-трассой, использование предсобранного рантайма, рандомизацию через Z3, pyslang, Verible и `apx-run`, в том числе под `docker exec -t`, протокол `apx_tb_pkg` исполнитель судьи `LocalDockerExecutor` (`tests/test_executor.py`) этап `precheck` на pyslang образа (`tests/test_precheck.py`) пайплайны `precheck → lint` (`tests/test_lint.py`) и `precheck → lint → sim` с окном трассы (`tests/test_sim.py`), CLI судьи `new → validate → run` (`tests/test_cli.py`). Другой тег образа — через `TOOLCHAIN_IMAGE`.

## Публикация

Workflow `.github/workflows/toolchain.yml` при изменениях в `toolchain/` или в коде судьи (`judge/src/`, `judge/poetry.lock`) собирает образ и прогоняет его тесты — они проверяют и судью против образа. Новый профиль нужен только при изменении входов образа: `Dockerfile`, `versions.lock`, `apx-run/`, `apx-verilate/`, `sv/`. Тогда на push в `master` CI публикует `ghcr.io/apparatica/toolchain:<TOOLCHAIN_PROFILE>` и `:sha-<коммит>`; тег профиля неизменяем: если он уже опубликован, CI падает с просьбой увеличить `TOOLCHAIN_PROFILE`, в том числе на pull request. Изменения тестов и документации образа ничего не публикуют.

Образ собирается только для `linux/amd64`.
