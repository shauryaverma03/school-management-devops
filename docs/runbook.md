# Operations runbook

## Deploy and inspect
Run docker compose up --build -d, then docker compose ps.
Check curl -k https://localhost:8443/health and /ready.
Read docker compose logs --tail=100 app db proxy.
Liveness checks the process. Readiness checks database connectivity.

## Restart and incident response
Run docker compose restart app. If readiness fails, inspect database health and logs, credentials and persistent disk space. Avoid deleting volumes during troubleshooting.
For a controlled drill, run docker compose stop db, request /ready and capture its failure plus logs. Run docker compose start db and verify readiness recovers. Health checks report failure; restart policies act on process exits, not merely unhealthy status.

## Backup and restore
Run sh scripts/backup.sh. Store the returned path securely.
Restoring replaces database contents with the backup. In the synthetic demo, create attendance, back up, capture a row count, restore with sh scripts/restore.sh backups/FILE.sql, and verify records and readiness.
Inspect records with docker compose exec db psql -U school -c 'TABLE attendance'.
The restore script stops app writes and restarts the app even if restore fails. A failed restore needs diagnosis before the deployment is considered healthy.

## Rollback
Retain the preceding Docker image before releasing. Set IMAGE_TAG to that previous commit tag in .env and run docker compose up -d --no-build app. Check readiness and the attendance workflow. Application rollback assumes compatible database schema. If restoring data is needed, take a current backup first and use the tested restore procedure.

## Demo recording
Use 3–5 minutes to show the architecture and passing pipeline, deployed health endpoint, teacher attendance and rejected unauthorized requests, logs and database failure/recovery, then backup/restore evidence. Keep tokens and .env out of the recording.

## Evidence
Save real outputs and screenshots in docs/evidence, add links in README, and record the final commit ID and image tag. Verify reviewer access to the repository and video.
