#!/usr/bin/env bash
# Roll back the last upgrade made with upgrade.sh.
#
#   infrastructure/deploy/rollback.sh                    # keep data entered since the upgrade
#   infrastructure/deploy/rollback.sh --restore-backup   # return to the pre-upgrade backup
#
# Default: if the upgrade changed the database schema, the NEW release's migrations are
# reversed first (alembic downgrade, which keeps work entered since the upgrade but drops
# any data stored only in new columns/tables), then the previous images and commit are
# started again.
# --restore-backup instead restores the backup taken just before the upgrade. Everything
# entered since the upgrade is lost; use it only if the downgrade fails or data is damaged.
set -euo pipefail
. "$(dirname "$0")/../backups/lib.sh"

STATE="$REPO_ROOT/.deploy/last-upgrade"
[ -f "$STATE" ] || die "no upgrade recorded ($STATE missing)"
previous_commit="$(grep '^previous_commit=' "$STATE" | cut -d= -f2)"
previous_revision="$(grep '^previous_revision=' "$STATE" | cut -d= -f2)"
backup="$(grep '^backup=' "$STATE" | cut -d= -f2-)"
for image in workshoppro-backend workshoppro-frontend; do
  docker image inspect "$image:previous" >/dev/null 2>&1 || die "$image:previous image is missing"
done

current_revision="$(dc exec -T postgres psql -X -At -U "$PGUSER_" -d "$PGDB_" \
  -c 'SELECT version_num FROM alembic_version')"
log "Rolling back to commit ${previous_commit:0:12} (schema $previous_revision; now $current_revision)"

if [ "${1:-}" = "--restore-backup" ]; then
  restore_needed=1
else
  restore_needed=0
  if [ "$current_revision" != "$previous_revision" ]; then
    log "Reversing migrations with the current release: $current_revision -> $previous_revision"
    dc stop nginx frontend worker backend >/dev/null
    dc run --rm --no-deps -e RUN_MIGRATIONS=false backend alembic downgrade "$previous_revision" \
      || die "downgrade failed; rerun with --restore-backup to restore $(basename "$backup")"
  fi
fi

for image in workshoppro-backend workshoppro-frontend; do
  docker tag "$image:previous" "$image:latest"
done
git checkout --quiet "$previous_commit"

if [ "$restore_needed" = 1 ]; then
  "$REPO_ROOT/infrastructure/backups/restore.sh" "$backup"
else
  dc up -d --remove-orphans
fi
for svc in backend worker frontend nginx; do wait_healthy "$svc" 300; done
log "Rolled back to commit ${previous_commit:0:12}. Note the checkout is now detached; see docs/deployment/upgrades.md"
