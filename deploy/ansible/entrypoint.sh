#!/bin/sh
# The keys mounted from Windows or macOS have modes ssh refuses: a copy with the right ones.
set -eu
if [ -d /ssh ]; then
    mkdir -p -m 700 "$HOME/.ssh"
    cp -R /ssh/. "$HOME/.ssh/"
    chmod -R go-rwx "$HOME/.ssh"
fi
exec "$@"
