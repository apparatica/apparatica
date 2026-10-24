# Спайк S5: окно трассы FST

Стенд спайка S5. Отчёт и выводы — [docs/spikes/s5.md](../../docs/spikes/s5.md). Код в основную ветку не переносится.

- `fifo.sv` — FIFO с мутантом, ошибка проявляется на такте, зависящем от сида;
- `apx_window_pkg.sv` — часть `apx_tb_pkg`, отвечающая за окно трассы;
- `tb.sv` — случайные push/pop против модели;
- `run.sh` — все замеры;
- `Dockerfile.analysis` — образ тулчейна плюс `fst2vcd` (GTKWave) для разбора FST.

Запуск (нужен собранный `apparatica-toolchain:dev`):

```sh
docker build -f Dockerfile.analysis -t apx-s5-analysis .
docker run --rm --network=none --read-only \
  --tmpfs /work:exec,size=512m,uid=10001,gid=10001 --tmpfs /tmp:size=64m \
  --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=256 --memory=2g --cpus=2 \
  -v "$PWD:/spike:ro" apx-s5-analysis sh /spike/run.sh
```
