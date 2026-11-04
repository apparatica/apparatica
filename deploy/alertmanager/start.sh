#!/bin/sh
# Alertmanager of the monitoring (docs/alerts.md) with its configuration written from the environment:
# with TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID the alerts go to that Telegram chat, without them (the
# stand) nowhere — they are seen in Grafana only.
#
#   start.sh [ARGS]   Alertmanager with ARGS
#   start.sh check    the configuration checked with amtool instead (`just alerts-test`)
set -eu
config=/tmp/alertmanager.yml

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    # A token is digits, a colon and [A-Za-z0-9_-]; a chat id is an integer, negative for groups.
    case ${TELEGRAM_BOT_TOKEN:-} in
    '' | *[!0-9A-Za-z:_-]*)
        echo "start.sh: TELEGRAM_BOT_TOKEN is not a bot token" >&2
        exit 1
        ;;
    esac
    case ${TELEGRAM_CHAT_ID:-} in
    '' | *[!0-9-]* | ?*-*)
        echo "start.sh: TELEGRAM_CHAT_ID is not a chat id" >&2
        exit 1
        ;;
    esac
    receiver=telegram
else
    receiver=none
fi

cat >"$config" <<EOF
templates:
  - /etc/apparatica/alertmanager/*.tmpl
route:
  receiver: $receiver
  group_by: [alertname, site]
  group_wait: 30s
  group_interval: 5m
  # A problem that lasts is repeated twice a day, not every few hours.
  repeat_interval: 12h
receivers:
  - name: none
EOF
if [ "$receiver" = telegram ]; then
    cat >>"$config" <<EOF
  - name: telegram
    telegram_configs:
      - bot_token: '$TELEGRAM_BOT_TOKEN'
        chat_id: $TELEGRAM_CHAT_ID
        message: '{{ template "apparatica.telegram" . }}'
        # Plain text: the annotations are not escaped for HTML.
        parse_mode: ''
        send_resolved: true
EOF
fi
chmod 600 "$config"

if [ "${1:-}" = check ]; then
    exec amtool check-config "$config"
fi
# A single instance: no cluster of Alertmanagers to gossip with.
exec /bin/alertmanager --config.file="$config" --storage.path=/alertmanager --cluster.listen-address= "$@"
