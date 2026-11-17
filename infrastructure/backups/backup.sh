#!/usr/bin/env bash
# Back up a WorkshopPro installation: database, object storage and a manifest.
#
#   infrastructure/backups/backup.sh [backup-root]
#
# Writes <backup-root>/<UTC timestamp>/ (default root: $BACKUP_DIR or ./backups):
#   database.dump   pg_dump custom format
#   objects.tar     every photo/document in object storage
#   manifest.json   schema revision and row counts (same snapshot as the dump), object count
#   SHA256SUMS      checksums, checked by restore.sh
# Backups older than $BACKUP_KEEP_DAYS days (default 14) are removed afterwards.
# Backups contain customer data: keep them private and copy them off this server
# (docs/deployment/backups.md).
set -euo pipefail
. "$(dirname "$0")/lib.sh"

ROOT="${1:-$(env_value BACKUP_DIR "$REPO_ROOT/backups")}"
KEEP_DAYS="$(env_value BACKUP_KEEP_DAYS 14)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$ROOT/$STAMP.partial"
umask 077
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' ERR

log "Backing up project '${COMPOSE_PROJECT_NAME:-workshoppro}' to $ROOT/$STAMP"

# One psql session holds a REPEATABLE READ snapshot open; pg_dump and the row counts
# both read that snapshot, so the manifest describes exactly what was dumped.
coproc PSQL { dc exec -T postgres psql -X -q -At -v ON_ERROR_STOP=1 -U "$PGUSER_" -d "$PGDB_"; }
psql_in="${PSQL[1]}"; psql_out="${PSQL[0]}"
echo "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT pg_export_snapshot();" >&"$psql_in"
read -r -t 60 SNAPSHOT <&"$psql_out" || die "could not open a database snapshot"

dc exec -T postgres pg_dump -U "$PGUSER_" -d "$PGDB_" --format=custom --snapshot="$SNAPSHOT" \
  > "$WORK/database.dump"
log "Database dumped ($(du -h "$WORK/database.dump" | cut -f1))"

cat >&"$psql_in" <<'SQL'
SELECT json_build_object(
  'alembic_revision', (SELECT version_num FROM alembic_version),
  'tables', (SELECT json_object_agg(table_name, (xpath('/row/n/text()',
      query_to_xml(format('SELECT count(*) AS n FROM public.%I', table_name), false, true, '')))[1]::text::bigint)
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE' AND table_name <> 'alembic_version'));
COMMIT;
SQL
read -r -t 120 SNAPSHOT_JSON <&"$psql_out" || die "could not read row counts"
exec {psql_in}>&-
wait "$PSQL_PID" 2>/dev/null || true

dc exec -T backend python -m app.cli storage-export > "$WORK/objects.tar"
printf '%s' "$SNAPSHOT_JSON" | dc exec -T backend python -m app.cli backup-manifest --snapshot-stdin \
  > "$WORK/manifest.json"
log "Objects exported ($(du -h "$WORK/objects.tar" | cut -f1))"

(cd "$WORK" && sha256sum database.dump objects.tar manifest.json > SHA256SUMS)
mv "$WORK" "$ROOT/$STAMP"
trap - ERR
log "Backup complete: $ROOT/$STAMP"

find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime +"$KEEP_DAYS" -print \
  -exec rm -rf {} + | sed 's/^/Removed old backup: /' >&2
echo "$ROOT/$STAMP"
