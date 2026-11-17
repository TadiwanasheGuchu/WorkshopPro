#!/usr/bin/env bash
# Health check for a WorkshopPro server. Run from cron every 5 minutes:
#
#   */5 * * * * cd /opt/workshoppro && infrastructure/monitoring/check.sh >> /var/log/workshoppro-monitor.log 2>&1
#
# Checks: every service running and healthy; API ready (database + Redis); latest backup
# age; disk space; TLS certificate expiry; notifications failing or stuck.
# Prints one line per check and exits 1 if any problem was found.
#
# Settings are read from the environment, then .env.
# Alerts (optional, sent only when the set of problems changes, including recovery):
#   ALERT_WEBHOOK_URL   POSTs {"text": "..."} (Slack/Teams/Google Chat style incoming webhook)
#   ALERT_EMAIL         uses the server's `mail` command, if installed
# Thresholds: BACKUP_DIR (default ./backups), BACKUP_MAX_AGE_HOURS (26),
# DISK_MAX_PERCENT (85), CERT_MIN_DAYS (21), TLS_CERT_DIR (./infrastructure/certs).
set -uo pipefail
. "$(dirname "$0")/../backups/lib.sh"

BACKUP_ROOT="$(env_value BACKUP_DIR "$REPO_ROOT/backups")"
MAX_AGE_H="$(env_value BACKUP_MAX_AGE_HOURS 26)"
DISK_MAX="$(env_value DISK_MAX_PERCENT 85)"
CERT_DAYS="$(env_value CERT_MIN_DAYS 21)"
ALERT_WEBHOOK_URL="$(env_value ALERT_WEBHOOK_URL "")"
ALERT_EMAIL="$(env_value ALERT_EMAIL "")"
CERT_FILE="$(env_value TLS_CERT_DIR "$REPO_ROOT/infrastructure/certs")/fullchain.pem"
STATE_FILE="${MONITOR_STATE_FILE:-${TMPDIR:-/tmp}/workshoppro-monitor-${COMPOSE_PROJECT_NAME:-workshoppro}.state}"

problems=()
ok() { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; problems+=("$*"); }

# 1. Services
expected="$(dc config --services 2>/dev/null | sort)"
[ -n "$expected" ] || bad "docker compose configuration could not be read"
for svc in $expected; do
  id="$(dc ps -q "$svc" 2>/dev/null)"
  if [ -z "$id" ]; then bad "service $svc is not running"; continue; fi
  state="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$id")"
  case "$state" in
    "running healthy" | "running no-healthcheck") ok "service $svc ($state)" ;;
    *) bad "service $svc is $state" ;;
  esac
done

# 2. API readiness (database and Redis), checked from inside the backend container.
if ready="$(dc exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=5).read().decode())" 2>/dev/null)" \
  && printf '%s' "$ready" | grep -q '"status":"ok"'; then
  ok "API ready"
else
  bad "API is not ready: ${ready:-no response}"
fi

# 3. Latest backup
latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*Z' 2>/dev/null | sort | tail -n 1)"
if [ -z "$latest" ]; then
  bad "no backups found in $BACKUP_ROOT"
else
  age_h=$(( ($(date +%s) - $(stat -c %Y "$latest")) / 3600 ))
  if [ "$age_h" -gt "$MAX_AGE_H" ]; then bad "latest backup $(basename "$latest") is ${age_h}h old"
  else ok "latest backup $(basename "$latest") (${age_h}h old)"; fi
fi

# 4. Disk space (repository, backups, Docker data)
for path in "$REPO_ROOT" "$BACKUP_ROOT" "$(docker info -f '{{.DockerRootDir}}' 2>/dev/null)"; do
  [ -d "$path" ] || continue
  used="$(df -P "$path" | awk 'NR==2 {gsub("%", "", $5); print $5}')"
  if [ "$used" -ge "$DISK_MAX" ]; then bad "disk for $path is ${used}% full"
  else ok "disk for $path ${used}% used"; fi
done

# 5. TLS certificate (production layout only)
if [ -f "$CERT_FILE" ]; then
  if openssl x509 -checkend $((CERT_DAYS * 86400)) -noout -in "$CERT_FILE" >/dev/null; then
    ok "TLS certificate valid for more than $CERT_DAYS days"
  else
    bad "TLS certificate expires $(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2)"
  fi
fi

# 6. Customer notifications failing or stuck
counts="$(dc exec -T postgres psql -X -At -U "$PGUSER_" -d "$PGDB_" -c \
  "SELECT count(*) FILTER (WHERE status = 'failed' AND failed_at > now() - interval '24 hours'),
          count(*) FILTER (WHERE status = 'queued' AND created_at < now() - interval '30 minutes')
   FROM notifications" 2>/dev/null)"
if [ -z "$counts" ]; then
  bad "could not read notification status"
else
  IFS='|' read -r failed stuck <<<"$counts"
  [ "$failed" -eq 0 ] && ok "no failed notifications in 24h" || bad "$failed notifications failed in the last 24h (see Notifications screen)"
  [ "$stuck" -eq 0 ] && ok "no notifications stuck in queue" || bad "$stuck notifications queued for over 30 minutes (is the worker running?)"
fi

# Alert when the set of problems changes.
summary="$(printf '%s\n' "${problems[@]:-}" | sed '/^$/d')"
previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
if [ "$summary" != "$previous" ]; then
  printf '%s' "$summary" > "$STATE_FILE"
  host="$(hostname)"
  if [ -n "$summary" ]; then
    message="WorkshopPro on $host: ${#problems[@]} problem(s)
$summary"
  else
    message="WorkshopPro on $host: all checks OK again"
  fi
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    payload="$(printf '%s' "$message" | python3 -c 'import json,sys; print(json.dumps({"text": sys.stdin.read()}))' 2>/dev/null)"
    curl -fsS -m 10 -H 'Content-Type: application/json' -d "$payload" "$ALERT_WEBHOOK_URL" >/dev/null \
      || echo "alert webhook failed" >&2
  fi
  if [ -n "${ALERT_EMAIL:-}" ] && command -v mail >/dev/null; then
    printf '%s\n' "$message" | mail -s "WorkshopPro monitor: $host" "$ALERT_EMAIL"
  fi
fi

[ ${#problems[@]} -eq 0 ]
