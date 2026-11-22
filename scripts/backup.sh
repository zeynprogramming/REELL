#!/usr/bin/env bash
# Saves the database and the uploaded videos into ./backups (keeps the 7 newest of each).
# Copy the backups folder off the server too (for example: scp -r user@server:~/reel/backups .).
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
./scripts/prod.sh exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "backups/db-$STAMP.sql.gz"
./scripts/prod.sh exec -T backend tar czf - -C /data/uploads . > "backups/uploads-$STAMP.tar.gz"
ls -1t backups/db-*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm --
ls -1t backups/uploads-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm --
echo "Backup done: backups/db-$STAMP.sql.gz and backups/uploads-$STAMP.tar.gz"
