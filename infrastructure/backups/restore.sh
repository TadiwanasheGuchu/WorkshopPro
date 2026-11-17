#!/usr/bin/env bash
# Restore a backup made by backup.sh into this Compose project, then verify it.
#
#   infrastructure/backups/restore.sh <backup-dir> [--yes]
#
# REPLACES the project's database and overwrites stored files with the backup's copies.
# When the worker starts again it sends notifications that were still queued at backup
# time (the restore drill does not start the worker).
# Without --yes it asks for confirmation. The backend runs migrations on start, so a
# backup from an older release is upgraded automatically.
set -euo pipefail
. "$(dirname "$0")/lib.sh"

BACKUP="${1:?Usage: restore.sh <backup-dir> [--yes]}"
BACKUP="$(cd "$BACKUP" && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-workshoppro}"

for f in database.dump objects.tar manifest.json SHA256SUMS; do
  [ -f "$BACKUP/$f" ] || die "$BACKUP/$f is missing"
done
(cd "$BACKUP" && sha256sum --quiet -c SHA256SUMS) || die "checksums do not match; backup is damaged"
log "Checksums OK"

if [ "${2:-}" != "--yes" ]; then
  printf 'This replaces ALL data in project "%s" with the backup %s.\nType the project name to continue: ' \
    "$PROJECT" "$(basename "$BACKUP")" >&2
  read -r answer
  [ "$answer" = "$PROJECT" ] || die "not confirmed"
fi

log "Stopping application services"
dc stop nginx frontend worker backend >/dev/null 2>&1 || true
dc up -d postgres redis storage >/dev/null
wait_healthy postgres
wait_healthy storage

log "Replacing database $PGDB_"
dc exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$PGUSER_" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$PGDB_\" WITH (FORCE)" \
  -c "CREATE DATABASE \"$PGDB_\" OWNER \"$PGUSER_\""
dc exec -T postgres pg_restore -U "$PGUSER_" -d "$PGDB_" --no-owner --exit-on-error \
  < "$BACKUP/database.dump"

log "Starting backend (applies any newer migrations)"
dc up -d backend >/dev/null
wait_healthy backend
log "Restoring stored files"
dc exec -T backend python -m app.cli storage-import < "$BACKUP/objects.tar"

log "Verifying"
if ! dc exec -T backend python -m app.cli verify-restore --manifest - < "$BACKUP/manifest.json"; then
  die "verification failed; application left stopped (backend is up for inspection)"
fi

# RESTORE_START_SERVICES limits what starts afterwards (the drill omits the worker).
# shellcheck disable=SC2086
dc up -d ${RESTORE_START_SERVICES:-} >/dev/null
log "Restore complete"
