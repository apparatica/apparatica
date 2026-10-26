#!/bin/sh
# valkey-queue with the users of queue-users.acl.in; the passwords come from the environment.
set -eu
sed -e "s|@API_PASSWORD@|${API_PASSWORD}|" -e "s|@WORKER_PASSWORD@|${WORKER_PASSWORD}|" \
    -e "s|@INGEST_PASSWORD@|${INGEST_PASSWORD}|" /etc/apparatica/queue-users.acl.in | grep -v '^#' > /tmp/users.acl
exec valkey-server --appendonly yes --maxmemory-policy noeviction --aclfile /tmp/users.acl "$@"
