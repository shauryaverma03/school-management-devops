#!/bin/sh
set -eu
test -f "${1:?Usage: sh scripts/restore.sh backup.sql}"
docker compose stop app
trap 'docker compose start app' EXIT
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U school -d school < "$1"
