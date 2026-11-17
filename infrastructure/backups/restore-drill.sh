#!/usr/bin/env bash
# Restore drill: restore a backup into a separate, throwaway Compose project on other
# ports, verify it, check the app answers, then delete the drill project.
# The live installation is not touched.
#
#   infrastructure/backups/restore-drill.sh <backup-dir> [--keep]
#
# --keep leaves the drill running (web on http://localhost:$DRILL_WEB_PORT) for a manual
# look; remove it later with: COMPOSE_PROJECT_NAME=workshoppro-restore-drill docker compose down -v
set -euo pipefail
export COMPOSE_PROJECT_NAME="workshoppro-restore-drill"
. "$(dirname "$0")/lib.sh"

BACKUP="${1:?Usage: restore-drill.sh <backup-dir> [--keep]}"
export WEB_PORT="${DRILL_WEB_PORT:-3901}" POSTGRES_PORT=55901 REDIS_PORT=56901 MAILPIT_PORT=8901

cleanup() {
  [ "${2:-}" = "--keep" ] && return
  log "Removing drill project"
  # Only ever the throwaway drill project and its volumes.
  [ "$COMPOSE_PROJECT_NAME" = "workshoppro-restore-drill" ] && dc down -v --remove-orphans >/dev/null 2>&1
}
trap 'cleanup "$@"' EXIT

log "Starting empty drill project on port $WEB_PORT"
dc up -d --no-build >/dev/null
wait_healthy backend 240

"$REPO_ROOT/infrastructure/backups/restore.sh" "$BACKUP" --yes

wait_healthy backend
code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/api/v1/health/ready")"
[ "$code" = 200 ] || die "restored app is not ready (HTTP $code)"
code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/sign-in")"
[ "$code" = 200 ] || die "sign-in page did not load (HTTP $code)"
log "Restore drill passed for $(basename "$BACKUP")"
