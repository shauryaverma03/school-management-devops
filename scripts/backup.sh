#!/bin/sh
set -eu
umask 077
mkdir -p backups
destination="backups/school-$(date +%Y%m%d-%H%M%S).sql"
docker compose exec -T db pg_dump -U school --clean --if-exists school > "$destination.tmp"
mv "$destination.tmp" "$destination"
echo "$destination"
