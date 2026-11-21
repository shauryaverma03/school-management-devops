#!/bin/sh
set -eu
test -f "${1:?Usage: sh scripts/restore-k8s.sh backup.sql}"
replicas=$(kubectl -n school get deployment school-api -o jsonpath='{.spec.replicas}')
kubectl -n school scale deployment school-api --replicas=0
trap 'kubectl -n school scale deployment school-api --replicas="$replicas"' EXIT
kubectl -n school wait --for=delete pod -l app=school-api --timeout=120s
kubectl -n school exec -i db-0 -- psql -v ON_ERROR_STOP=1 --single-transaction -U school -d school < "$1"
