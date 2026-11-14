#!/bin/bash
set -euo pipefail
python scripts/init-env.py
set -a
source .env
set +a
export LOCAL_TLS=1
docker compose up --build --wait --wait-timeout 180
python scripts/smoke.py
backup=$(sh scripts/backup.sh)
before=$(docker compose exec -T db psql -U school -Atc "SELECT COUNT(*) FROM attendance")
docker compose exec -T db psql -U school -c "DELETE FROM attendance"
sh scripts/restore.sh "$backup"
after=$(docker compose exec -T db psql -U school -Atc "SELECT COUNT(*) FROM attendance")
test "$before" = "$after"
docker compose stop db
code=$(curl -ks -o /dev/null -w '%{http_code}' https://localhost:8443/ready)
test "$code" = 503
docker compose start db
for attempt in {1..30}; do
  if curl -kfsS https://localhost:8443/ready; then
    echo "Backup restore and database failure recovery verified."
    exit 0
  fi
  sleep 2
done
exit 1
