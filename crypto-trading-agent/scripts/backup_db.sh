#!/bin/sh
# Nightly Postgres backup with retention. Runs standalone (cron) or as the compose
# `backup` service (profile "ops"), which loops daily.
#
#   POSTGRES_URL     connection string to back up (required)
#   BACKUP_DIR       where dumps land            (default /backups)
#   BACKUP_KEEP_DAYS retention in days           (default 14)
#
# ⚠️ Restores of exchange keys also require the SAME VAULT_ENC_KEY — keep it in your
# secret manager alongside these dumps (see docs/OPERATIONS.md).
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

if [ -z "${POSTGRES_URL:-}" ]; then
    echo "POSTGRES_URL is not set — nothing to back up" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y-%m-%d_%H%M)"
out="$BACKUP_DIR/cryptai-$stamp.dump"

echo "[backup] dumping to $out"
pg_dump "$POSTGRES_URL" --no-owner --format=custom --file="$out"
echo "[backup] done: $(du -h "$out" | cut -f1)"

# Retention: drop dumps older than KEEP_DAYS.
find "$BACKUP_DIR" -name 'cryptai-*.dump' -mtime "+$KEEP_DAYS" -delete
echo "[backup] retention applied (>${KEEP_DAYS}d removed)"
