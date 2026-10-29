# worker

Воркер Apparatica: Dramatiq-актор проверки и оркестратор песочницы (пакет `apparatica_worker`). Зависит от `judge`.

```sh
APX_QUEUE_URL=redis://localhost:6379/0 poetry -C worker run apparatica-worker
APX_SANDBOXD_RUNTIME=runc APX_SANDBOXD_SOCKET=/tmp/sandboxd.sock poetry -C worker run apx-sandboxd   # Linux
```

`apx-sandboxd` — демон песочницы на хосте воркера ([architecture.md](../docs/architecture.md#песочница-apx-sandboxd)), единственный процесс с доступом к Docker. Он слушает unix-сокет, поэтому на Windows не запускается; его тесты поднимают его на `127.0.0.1`. Тесты против образа тулчейна (`-m image`) запускает `just toolchain-test`.

`Dockerfile` — образ обоих процессов для стенда (`deploy/compose.yaml`, сервисы `worker` и `sandboxd`; [docs/stand.md](../docs/stand.md#воркер-и-песочница)).

Устройство — [docs/architecture.md](../docs/architecture.md#очередь-проверок) (очередь, [оркестратор](../docs/architecture.md#оркестратор), [стримы](../docs/architecture.md#стримы-проверки)), безопасность — [docs/security.md](../docs/security.md), настройки — [docs/configuration.md](../docs/configuration.md#воркер), разработка — [docs/development.md](../docs/development.md#воркер).
