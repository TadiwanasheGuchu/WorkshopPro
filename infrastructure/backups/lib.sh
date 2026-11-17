# Shared helpers for backup.sh, restore.sh and restore-drill.sh. Sourced, not run.
# Commands run through Docker Compose from the repository root, so the same scripts
# work for any Compose project (COMPOSE_PROJECT_NAME selects which one).

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# .env uses Compose syntax (not shell), so read just the values needed here.
env_value() {  # env_value NAME DEFAULT: environment first, then .env, then the default
  local value="${!1:-}"
  if [ -z "$value" ] && [ -f .env ]; then
    value="$(grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
  fi
  printf '%s' "${value:-$2}"
}
PGUSER_="$(env_value POSTGRES_USER workshoppro)"
PGDB_="$(env_value POSTGRES_DB workshoppro)"

dc() { docker compose "$@"; }
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

wait_healthy() {  # wait_healthy <service> [seconds]
  local service="$1" limit="${2:-180}" waited=0 id state
  while :; do
    id="$(dc ps -q "$service")"
    state="$( [ -n "$id" ] && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" || echo missing)"
    # Health status when the service defines a healthcheck, otherwise "running".
    case "$state" in healthy|running) return 0;; esac
    [ "$waited" -ge "$limit" ] && die "$service is not healthy after ${limit}s (state: $state)"
    sleep 3; waited=$((waited + 3))
  done
}
