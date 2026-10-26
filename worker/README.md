# worker

Воркер Apparatica: Dramatiq-актор проверки и оркестратор песочницы (пакет `apparatica_worker`). Зависит от `judge`.

```sh
APX_QUEUE_URL=redis://localhost:6379/0 poetry -C worker run apparatica-worker
```

Устройство — [docs/architecture.md](../docs/architecture.md#очередь-проверок), настройки — [docs/configuration.md](../docs/configuration.md#воркер), разработка — [docs/development.md](../docs/development.md#воркер).
