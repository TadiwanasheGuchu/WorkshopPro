#!/bin/sh
set -e

# Apply pending migrations before serving. Set RUN_MIGRATIONS=false to skip
# (for example when running several API replicas behind one migration job).
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"
