#!/usr/bin/env bash
# Online backup of MannyFi's databases (orders, trading keys, passkeys, sessions). Keeps 14 days.
# Trading keys inside are encrypted with SARF_SESSION_SECRET, which is NOT in the backup: keep .env safe separately.
# Run daily, for example:  17 3 * * * /root/hashbit/deploy/backup.sh >> /root/backups/mannyfi/backup.log 2>&1
set -euo pipefail
umask 077
OUT=/root/backups/mannyfi
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
for db in basket grants; do
  sqlite3 "/root/hashbit/server/data/$db.db" ".backup '$OUT/$db-$STAMP.db'"
done
find "$OUT" -name '*.db' -mtime +14 -delete
