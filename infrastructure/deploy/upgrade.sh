#!/usr/bin/env bash
# Upgrade a WorkshopPro installation, with a backup and a recorded rollback point.
#
#   infrastructure/deploy/upgrade.sh [git-ref]
#
# 1. Takes a backup (infrastructure/backups/backup.sh).
# 2. Tags the running images as :previous and records the commit and schema revision
#    in .deploy/last-upgrade, for rollback.sh.
# 3. Checks out git-ref (a release tag) if given; otherwise deploys the current checkout.
# 4. Builds the images (SKIP_BUILD=1 to use images built elsewhere), starts the stack;
#    the backend applies migrations on start.
# 5. Waits for every service to be healthy and the API to be ready.
# If step 5 fails, run infrastructure/deploy/rollback.sh.
set -euo pipefail
. "$(dirname "$0")/../backups/lib.sh"

REF="${1:-}"
STATE_DIR="$REPO_ROOT/.deploy"
mkdir -p "$STATE_DIR"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  die "the checkout has local changes; commit or remove them first (git status)"
fi

prev_commit="$(git rev-parse HEAD)"
prev_revision="$(dc exec -T postgres psql -X -At -U "$PGUSER_" -d "$PGDB_" \
  -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)"
[ -n "$prev_revision" ] || die "could not read the current schema revision; is the stack running?"

log "Backing up before upgrade"
backup="$("$REPO_ROOT/infrastructure/backups/backup.sh" | tail -n 1)"

for image in workshoppro-backend workshoppro-frontend; do
  docker image inspect "$image:latest" >/dev/null 2>&1 && docker tag "$image:latest" "$image:previous"
done
cat > "$STATE_DIR/last-upgrade" <<EOF
upgraded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
previous_commit=$prev_commit
previous_revision=$prev_revision
backup=$backup
EOF
log "Rollback point recorded: commit ${prev_commit:0:12}, schema $prev_revision, backup $(basename "$backup")"

if [ -n "$REF" ]; then
  log "Checking out $REF"
  git fetch --tags origin
  git checkout --quiet "$REF"
fi
log "Deploying commit $(git rev-parse --short HEAD)"

if [ "${SKIP_BUILD:-}" != 1 ]; then
  log "Building images"
  dc build backend frontend
fi

dc up -d --remove-orphans
for svc in backend worker frontend nginx; do wait_healthy "$svc" 300; done
new_revision="$(dc exec -T postgres psql -X -At -U "$PGUSER_" -d "$PGDB_" -c 'SELECT version_num FROM alembic_version')"
dc exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=5)" \
  || die "API is not ready; run infrastructure/deploy/rollback.sh"

log "Upgrade complete: commit $(git rev-parse --short HEAD), schema $prev_revision -> $new_revision"
log "If staff report problems, roll back with: infrastructure/deploy/rollback.sh"
