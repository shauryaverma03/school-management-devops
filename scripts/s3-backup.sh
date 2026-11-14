#!/bin/sh
set -eu
: "${BACKUP_BUCKET:?Set BACKUP_BUCKET from Terraform output}"
file=$(sh scripts/backup-k8s.sh)
aws s3 cp "$file" "s3://$BACKUP_BUCKET/database/$(basename "$file")" --sse AES256
