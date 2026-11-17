#!/usr/bin/env bash
# Create (or recreate) the workshoppro_perf database on the local PostgreSQL, migrate it,
# create an organisation and seed about three years of data. Development only.
#   PGPASSWORD=... scripts/perf/reset.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${PGHOST:=localhost}" "${PGUSER:=workshoppro}"
export PGHOST PGUSER
psql -d postgres -qc "DROP DATABASE IF EXISTS workshoppro_perf" -c "CREATE DATABASE workshoppro_perf"
export DATABASE_URL="postgresql+psycopg://${PGUSER}:${PGPASSWORD:-workshoppro}@${PGHOST}:5432/workshoppro_perf"
uv run alembic upgrade head
printf 'perf-owner-password-1\n' | uv run python -m app.cli create-organisation \
  --name "Perf Motors" --owner-email perf-owner@example.com --owner-name "Perf Owner" --password-stdin
psql -d workshoppro_perf -q -f scripts/perf/seed.sql
