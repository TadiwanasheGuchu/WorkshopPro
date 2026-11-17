#!/bin/sh
set -e

# Apply pending migrations before serving. Set RUN_MIGRATIONS=false to skip
# (for example when running several API replicas behind one migration job).
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
  # Hosted demo only: create the demo organisation on first start (empty database).
  if [ -n "${DEMO_PASSWORD:-}" ]; then
    python -m app.cli seed-demo --if-empty || echo "Demo seed failed; the app starts without it." >&2
  fi
fi

exec "$@"
