# Образ тулчейна

Образ, в котором песочница выполняет все этапы проверки (ADR-0003, specs/07 §5). Один опубликованный образ — один профиль тулчейна (`ToolchainProfile`): результаты сравнимы только в пределах профиля.

Сейчас собран профиль 2: Verilator, Z3, pyslang, Verible, `apx-run`, `apx-verilate`, `apx-init`, библиотека тестбенча `apx_tb_pkg`, а для синтеза — Yosys со встроенным sv-elab, OpenSTA и liberty Nangate45 (с T3.1a). SymbiYosys добавится в T5.1.

## Состав

| Что | Где | Откуда |
|---|---|---|
| Verilator | `/opt/verilator` | исходники с GitHub по тегу, sha256 в `versions.lock` |
| Рантайм Verilator, предсобранный | `/opt/apx/verilator-runtime/libverilated_apx.a` | собирается при сборке образа (`apx-verilate/build-runtime.sh`) |
| Verible | `/opt/verible` | статическая сборка с GitHub, sha256 в `versions.lock` |
| pyslang | `/opt/apx/venv` (первый в `PATH` Python) | колесо PyPI по хэшу |
| Z3, g++, make, Python 3.13 | пакеты Debian trixie | версии проверяют тесты образа |
| Yosys с ABC и sv-elab (бывший yosys-slang) | `/opt/yosys` | релизный `yosys.tar.gz` с подмодулями, sha256 в `versions.lock`; сборка CMake |
| OpenSTA (только `sta`) с CUDD | `/opt/opensta/bin/sta` | исходники `parallaxsw/OpenSTA` по коммиту и CUDD по тегу, sha256 в `versions.lock`; CUDD и Eigen (заголовки Debian) встроены статически |
| liberty Nangate45 с `LICENSE` и `README.md` | `/opt/pdk/nangate45` | OpenROAD-flow-scripts по коммиту, sha256 каждого файла в `versions.lock` |
| `apx-run`, `apx-verilate`, `apx-init` | `/opt/apx/bin` | этот каталог |
| `apx_tb_pkg.sv` | `/opt/apx/sv` | `sv/` |
| Лицензии Verilator, Verible, Yosys (со встроенными библиотеками), OpenSTA, CUDD, Eigen | `/opt/licenses` | из исходников; лицензии пакетов Debian — в `/usr/share/doc/*/copyright` |
| Где взять исходные тексты программ образа | `/opt/licenses/SOURCES.md` | `SOURCES.md.in` с версиями из `versions.lock` и списком установленных пакетов Debian (ADR-0012) |

Команды выполняются от непривилегированного пользователя `sandbox` (UID 10001), рабочий каталог и `HOME` — `/work`. В песочнице корневая ФС только для чтения, `/work` — tmpfs.

## `apx-run`

Под `docker exec -t` stderr сливается со stdout. `apx-run COMMAND [ARGS...]` даёт команде отдельные псевдотерминалы для stdout и stderr — инструменты видят TTY и выводят построчно — и пишет оба потока в свой stdout:

- строки stdout — как есть;
- строки stderr — с байтом `0x1E` (ASCII record separator) в начале; оркестратор снимает его и назначает канал `err`;
- строки разных потоков не склеиваются; без перевода строки хвост выводится после 50 мс тишины;
- код выхода — код команды, `128+N` при гибели от сигнала N, `127`, если команду не удалось запустить;
- после выхода команды `apx-run` ждёт вывод оставшихся процессов не дольше 200 мс; убивает их оркестратор (specs/07 §5.2).

Метка канала косметическая: вердикт от неё не зависит, подделка из `$display` меняет только цвет строки.

## `apx-init`

Команда контейнера по умолчанию (`CMD`) и его PID 1 (S6). Между этапами оркестратор выполняет `kill -KILL -1` от пользователя песочницы. Ядро не доставляет этот сигнал PID 1, поэтому контейнер продолжает работать, а убитые процессы этапа становятся детьми `apx-init`, и он их забирает. С `sleep infinity` они оставались бы зомби и занимали `--pids-limit`, а `docker run --init` завершается вместе со своим единственным ребёнком. `SIGTERM` и `SIGINT` (`docker stop`) завершают `apx-init` и контейнер.

## `apx-verilate`

`apx-verilate [АРГУМЕНТЫ VERILATOR...]` — Verilator с флагами `--binary --timing --trace-fst`, для которых собран рантайм в образе. Рантайм не компилируется на каждую отправку: `make` получает пустые `VM_GLOBAL_FAST`/`VM_GLOBAL_SLOW`, а объекты берутся из `libverilated_apx.a`. Остальные флаги (`--x-assign`, `--x-initial`, `-Wno-*`, `-j`, исходники, `--top-module`) передаёт этап `sim` (specs/07 §2.3).

Флаги, влияющие на рантайм, менять только здесь: библиотека совпадает с ними. При сборке образа `build-runtime.sh` компилирует эталонный тестбенч `runtime_ref.sv` со всеми нужными частями рантайма (timing, FST, рандомизация, потоки) и падает, если набор объектов изменился.

## `apx_tb_pkg`

Библиотека тестбенчей задач (specs/06 §3.2): плюс-аргументы, группы, счётчик тактов, протокол результатов в файл JSON Lines и строки прогресса `@@apx:<nonce>` в stdout, лимит тактов, окно трассы FST. Этап `sim` компилирует `/opt/apx/sv/apx_tb_pkg.sv` первым, с `--timescale 1ps/1ps` (specs/07 §2.3). Разбор протокола на стороне судьи — `judge/src/judge/languages/systemverilog/tbproto.py`; тесты образа `tests/test_apx_tb_pkg.py` собирают тестбенч с библиотекой и разбирают результат этим модулем.

Правка библиотеки — изменение образа: новый `TOOLCHAIN_PROFILE`. Задачи, собранные со старым профилем, продолжают работать со старой версией библиотеки.

## Синтез

Этап `synth` (specs/07 §2.4, [docs/judge.md](../docs/judge.md#systemverilog-synth)) вызывает `yosys` и `sta` из `PATH`; liberty — `/opt/pdk/nangate45/NangateOpenCellLibrary_typical.lib`. Ключ `NANGATE45_LIB_SHA256` даёт и имя библиотеки профиля (`ToolchainProfile.liberty` = `nangate45`, по ключу `<ИМЯ>_LIB_SHA256`).

- **sv-elab** (бывший yosys-slang) встроен в Yosys с 0.67: `read_slang` доступен без `plugin -i`. Его slang — тот же коммит, что у pyslang этапа `precheck` (`SLANG_COMMIT` в `versions.lock`, ADR-0007): оба этапа разбирают код одной версией. В релизном архиве Yosys нет `.git`, поэтому ревизию для `slang_version` сборка берёт из `libs/slang/.git_archival.txt` и падает, если она не совпадает с `SLANG_COMMIT`. Обновлять Yosys и pyslang нужно вместе: новая версия Yosys с другим slang требует pyslang на том же коммите.
- **OpenSTA** собирается из коммита `parallaxsw/OpenSTA`; в образ попадает только программа `sta`.

### Nangate45

Liberty, `LICENSE` и `README.md` (версия `PDKv1.3_v2010_12.Apache.CCL` и источник) взяты из OpenROAD-flow-scripts без изменений; уведомление Nangate в заголовке liberty сохранено. Лицензия библиотеки — единственное исключение из списка открытых лицензий проекта (ADR-0007, NFR-MAINT-07, `scripts/license-policy.toml`): уведомление Nangate запрещает сравнивать библиотеку с другими и помечает её «not intended for commercial use», а `LICENSE` из OpenROAD-flow-scripts — Apache-2.0; что действует — открытый вопрос ОВ-21. Коммерческий форк или инстанс должен оценить лицензию сам. Тесты образа проверяют, что файлы лежат вместе, совпадают по sha256 и что исключение записано в политике лицензий.

## Версии и профиль

`versions.lock` — строки `KEY=value`: версии и sha256 загружаемых инструментов, ожидаемые версии пакетов Debian и `TOOLCHAIN_PROFILE`. Dockerfile читает его при сборке, тесты образа сверяют с ним установленные версии.

Пакеты Debian ставятся из текущего trixie поверх базового образа, закреплённого по digest. Если при пересборке apt поставит более новую версию, тесты образа упадут: обновите `versions.lock`. Профиль закрепляет опубликованный образ (его digest), а не возможность пересобрать его побайтно.

Как обновить инструмент:

1. Поменяйте версию и sha256 в `versions.lock`, увеличьте `TOOLCHAIN_PROFILE`. Профиль увеличивается при любом изменении образа, включая `apx-run`, `apx-verilate` и `apx_tb_pkg`.
2. `just toolchain-build && just toolchain-test && just security-test`.
3. После слияния в `master` CI публикует образ. Перевод задач на новый профиль — specs/09 §2.
4. Стенд переходит на новый профиль отдельным PR: digest опубликованного образа — в `deploy/compose.yaml`, у сервисов `toolchain` и `toolchain-profile` ([docs/stand.md](../docs/stand.md#воркер-и-песочница)).

## Сборка и тесты

```sh
just toolchain-build   # docker build → apparatica-toolchain:dev
just toolchain-test    # тесты образа: pytest на хосте, команды в контейнере песочницы
just security-test     # набор атак tests/security/ через apx-sandboxd (docs/security.md)
```

Если Docker Hub или `deb.debian.org` недоступны, задайте зеркала через переменные окружения:

```sh
TOOLCHAIN_BASE_IMAGE=mirror.gcr.io/library/debian@sha256:<digest из Dockerfile>
TOOLCHAIN_DEBIAN_MIRROR=http://mirror.yandex.ru/debian
```

Тесты образа (`tests/`) запускаются pytest на хосте из окружения `judge` (нужен Docker). Фикстура поднимает один контейнер с ограничениями песочницы specs/07 §5.1 (`tests/sandbox.py`) и выполняет каждую команду через `docker exec` — так же, как оркестратор выполняет этапы; инструменты тестирования в образ не попадают. Тесты проверяют версии, ограничения песочницы, сборку и симуляцию с FST-трассой, этап `synth` (метрики эталонов демо-задач — как в S4, латчи, петли, драйверы, ошибки sv-elab, кэш, побайтный повтор), совпадение slang в Yosys и pyslang, шаблоны триггеров и лицензии библиотеки (`tests/test_synthesis.py`), использование предсобранного рантайма, рандомизацию через Z3, pyslang, Verible и `apx-run`, в том числе под `docker exec -t`, протокол `apx_tb_pkg` `apx-init` как PID 1, `SOURCES.md`, исполнитель судьи `LocalDockerExecutor` (`tests/test_executor.py`) этап `precheck` на pyslang образа (`tests/test_precheck.py`) пайплайны `precheck → lint` (`tests/test_lint.py`) и `precheck → lint → sim` с окном трассы (`tests/test_sim.py`), CLI судьи `new → validate → run` (`tests/test_cli.py`). Другой тег образа — через `TOOLCHAIN_IMAGE`.

## Публикация

Workflow `.github/workflows/toolchain.yml` при изменениях в `toolchain/`, в коде судьи и воркера, в классах ресурсов или в `tests/security/` собирает образ и прогоняет его тесты — они проверяют и судью против образа, — а затем набор атак под gVisor. Провал любого из них не даёт опубликовать образ. Новый профиль нужен только при изменении входов образа: `Dockerfile`, `versions.lock`, `apx-run/`, `apx-verilate/`, `sv/`. Тогда на push в `master` CI публикует `ghcr.io/apparatica/toolchain:<TOOLCHAIN_PROFILE>` и `:sha-<коммит>`; тег профиля неизменяем: если он уже опубликован, CI падает с просьбой увеличить `TOOLCHAIN_PROFILE`, в том числе на pull request. Изменения тестов и документации образа ничего не публикуют.

Образ собирается только для `linux/amd64`.
