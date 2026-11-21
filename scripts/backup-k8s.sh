#!/bin/sh
set -eu
mkdir -p backups
file="backups/school-k8s-$(date +%Y%m%d-%H%M%S).sql"
umask 077
kubectl -n school exec db-0 -- pg_dump -U school --clean --if-exists school > "$file.tmp"
mv "$file.tmp" "$file"
echo "$file"
