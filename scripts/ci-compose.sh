#!/bin/bash
set -euo pipefail
python scripts/init-env.py
set -a
source .env
set +a
export LOCAL_TLS=1

wait_for_ready() {
  for attempt in {1..30}; do
    if curl -kfsS --connect-timeout 2 --max-time 5 -o /dev/null https://localhost:8443/ready; then
      return 0
    fi
    sleep 2
  done
  echo "API did not become ready through the proxy: $1" >&2
  docker compose ps -a >&2
  docker compose logs --no-color --tail=100 app proxy db >&2
  return 1
}

docker compose up --build --wait --wait-timeout 180
wait_for_ready "initial startup"
python scripts/smoke.py
backup=$(sh scripts/backup.sh)
before=$(docker compose exec -T db psql -U school -Atc "SELECT COUNT(*) FROM attendance")
docker compose exec -T db psql -U school -c "DELETE FROM attendance"
sh scripts/restore.sh "$backup"
after=$(docker compose exec -T db psql -U school -Atc "SELECT COUNT(*) FROM attendance")
test "$before" = "$after"
# Restore restarts the API; verify startup completed before injecting a DB outage.
wait_for_ready "backup restore"
docker compose stop db
code=$(curl -ksS --connect-timeout 2 --max-time 10 -o /dev/null -w '%{http_code}' https://localhost:8443/ready)
if [ "$code" != 503 ]; then
  echo "Expected readiness HTTP 503 with the database stopped, got $code" >&2
  exit 1
fi
docker compose start db
wait_for_ready "database recovery"
python scripts/smoke.py
echo "Backup restore and database failure recovery verified."
