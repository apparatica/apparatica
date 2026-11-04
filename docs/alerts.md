# Алерты

Алерты мониторинга (NFR-OBS-04): Prometheus проверяет правила, Alertmanager шлёт сообщения в Telegram. Сейчас правила есть только для бэкапов Postgres (NFR-REL-04, [backups.md](backups.md)). Остальные алерты NFR-OBS-04 — очередь, доля внутренних ошибок, место на диске — появятся с production (T3.14). Что делать, когда алерт пришёл, — в [RUNBOOK](../deploy/RUNBOOK.md#алерты).

## Как устроено

Юнит systemd → `apparatica-backup-metrics` → файл метрик → `node-exporter` → Prometheus и его правила → Alertmanager → Telegram:

1. После каждого запуска юнита бэкапа или проверки восстановления, удачного или нет, systemd запускает `apparatica-backup-metrics` (`ExecStopPost`). Скрипт читает итог из `SERVICE_RESULT` и пишет метрики задачи в `/var/lib/apparatica/metrics/<задача>.prom` (`apparatica_metrics_dir`). Файл пишется рядом и переименовывается, поэтому node-exporter никогда не прочитает половину. Скрипт ставит Ansible вместе с юнитами ([backups.md](backups.md#на-сервере)).
2. `node-exporter` читает эти файлы textfile-коллектором. На сервере ему смонтирован корень хоста только для чтения (`compose.server.yaml`): так же он отдаёт метрики дисков, памяти и процессора хоста для будущих алертов.
3. Prometheus раз в 15 с собирает метрики и проверяет правила `deploy/prometheus/rules/*.yml`. Каждый алерт получает метку `site` — имя сайта (`ALERT_SITE`: на сервере `SITE_HOST`), чтобы по сообщению было видно окружение.
4. Alertmanager группирует алерты и отправляет их в Telegram.

Сбор и отправка не зависят от того, работает ли сайт, но работают на том же хосте: если лежит сам хост, Prometheus или Alertmanager, сообщений не будет. Внешнего наблюдателя («dead man's switch») пока нет.

## Метрики бэкапов

У каждой метки `task`: `backup` — полный бэкап (`apparatica-backup.service`), `restore_check` — проверка восстановления (`apparatica-backup-check.service`).

| Метрика | Значение |
|---|---|
| `apparatica_backup_last_run_success` | `1`, если последний запуск удался, иначе `0` |
| `apparatica_backup_last_run_timestamp_seconds` | когда закончился последний запуск (Unix-время) |
| `apparatica_backup_last_success_timestamp_seconds` | когда закончился последний удачный запуск; неудачный запуск его не меняет, у задачи без удачных запусков метрики нет |

Без записи о запуске правила молчат, поэтому деплой с `apparatica_backups: true` сам делает недостающее: если записи о бэкапе нет, делает полный бэкап и ждёт его, если нет записи о проверке — запускает её в фоне. С `apparatica_backups: false` записи удаляются вместе с юнитами, и правила молчат.

## Правила

`deploy/prometheus/rules/backups.yml`:

| Алерт | Когда срабатывает |
|---|---|
| `BackupTooOld` | последнему удачному полному бэкапу больше 26 часов (суточный таймер, его задержка до 10 минут и сам бэкап), или удачных бэкапов не было вовсе |
| `RestoreCheckFailed` | последняя проверка восстановления не прошла; держится до удачной |
| `RestoreCheckTooOld` | удачной проверке больше 8 дней, а последняя не падала: еженедельный таймер не запускается |
| `HostMetricsMissing` | 15 минут нет метрик `node-exporter` или он не может прочитать файл метрик: без них правила выше не сработают |

Сбой архива WAL отдельным алертом не ловится, но доходит до `BackupTooOld`: полный бэкап проверяет непрерывность архива (`wal-verify`) и при дыре падает, а через 26 часов после последнего удачного срабатывает алерт.

## Доставка

Alertmanager (`deploy/alertmanager/start.sh`) собирает свою конфигурацию из окружения при запуске:

- `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` заданы — алерты идут в этот чат Telegram. Задан только один из них или значение неверного вида — Alertmanager не запускается.
- Не заданы (стенд) — алерты никуда не отправляются, их видно в Grafana: Alerting → Alert rules (правила Prometheus) и источник `Alertmanager` (активные алерты и заглушки).

Алерты группируются по имени и сайту: первое сообщение группы — через 30 с, новые алерты в ней — не чаще раза в 5 минут, напоминание о незакрытых — раз в 12 часов, о разрешении приходит «Отбой». Режим кластера выключен: Alertmanager один.

Сообщение — простой текст (шаблон `deploy/alertmanager/telegram.tmpl`):

```text
Тревога · staging.apparatica.app

Проверка восстановления бэкапа не прошла
Последний бэкап не восстановился или в восстановленной базе нет данных. Причина — в journalctl -u apparatica-backup-check. Алерт держится до удачной проверки.
Что делать: https://github.com/apparatica/apparatica/blob/master/deploy/RUNBOOK.md#бэкапы
```

В сообщениях нет персональных данных: только имя сайта и тексты правил.

### Бот и чат

Бота и чат создаёт оператор, один раз на окружение (или общий на все: сайт виден в сообщении):

1. В Telegram у [@BotFather](https://t.me/BotFather) — `/newbot`; он выдаёт токен вида `123456789:AA…`.
2. Чат для алертов: группа, в которую добавлен бот, или личный чат с ботом. Напишите в него что-нибудь и откройте `https://api.telegram.org/bot<токен>/getUpdates`: id чата — `result[].message.chat.id` (у групп отрицательный).
3. Токен — в `/etc/apparatica/secrets.env` сервера: `TELEGRAM_BOT_TOKEN=<токен>` (не генерируется, как и ключи хранилища бэкапов, [deployment.md](deployment.md#секреты)). Id чата — в инвентарь: `apparatica_alert_telegram_chat_id: <id>`.
4. `just deploy <окружение>`. Деплой останавливается, если задано только одно из двух.
5. Пробный алерт — [RUNBOOK](../deploy/RUNBOOK.md#алерты).

У staging — бот `@apparatica_status_bot` и личный чат с ним. Telegram API доступен с хоста staging (AEZA) по IPv4 и IPv6 (проверено в T2.10b).

## Проверка

`just alerts-test` (job `Alerts` в CI) в образах Prometheus и Alertmanager:

- `promtool check config` — конфигурация Prometheus и файлы правил;
- `promtool test rules` — модульные тесты правил `deploy/prometheus/tests/*.yml`: когда каждый алерт срабатывает и не срабатывает, его метки и тексты;
- `amtool check-config` — конфигурация `start.sh` без Telegram и с ним.

Тесты `scripts/test_backup_metrics.py` проверяют, что пишет `apparatica-backup-metrics`, и что правила читают только его метрики.
