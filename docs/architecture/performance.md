# Performance review

Target (CLAUDE.md §11): ordinary API calls under 500 ms at pilot load — measured, not
promised.

## Method

`backend/scripts/perf/` seeds a separate database with roughly **three years of a busy
single-branch workshop** (about 30 jobs per working day) and times the API calls behind
the main screens.

| Table | Rows |
|---|---|
| customers / contacts | 8,000 / 13,000 |
| vehicles | 10,000 |
| job cards / status history | 30,000 / 120,000 |
| invoices / payments | 23,920 / 22,425 |
| notifications | 60,000 |
| audit log | 360,000 |

```bash
cd backend
PGPASSWORD=<local password> scripts/perf/reset.sh          # ~25 s
DATABASE_URL=postgresql+psycopg://workshoppro:<password>@localhost:5432/workshoppro_perf \
  STORAGE_ACCESS_KEY=x STORAGE_SECRET_KEY=y RATE_LIMIT_ENABLED=false \
  uv run uvicorn app.main:app --port 8010 &
uv run python scripts/perf/measure.py --load
```

One API process (as in Compose), PostgreSQL 16 on the same machine. Each call is
repeated 7 times; the first run is discarded. Times include HTTP, authentication,
permission checks and JSON serialisation.

## Results (2026-11-17)

Every call is within target. Slowest single calls are the period reports (about 100–130
ms for a full year).

| Call | Before | After |
|---|---|---|
| Job cards: search by number | 322 ms | 47 ms |
| Job cards: search by registration | 353 ms | 43 ms |
| Job cards: search by customer name | 398 ms | 53 ms |
| Invoices: list, page 1 | 90 ms | 20 ms |
| Payments: list, page 1 | 123 ms (177 queries) | 18 ms (8 queries) |
| Payments: search | 152 ms | 34 ms |
| Job cards: open / all / completed | 31 / 57 / 48 ms | 26 / 41 / 45 ms |
| Dashboard summary | 27 ms | 18 ms |
| Customers: search name / phone / registration | 84 / 85 / 84 ms | 72 / 76 / 85 ms |
| Vehicles: search | 26 ms | 23 ms |
| Notifications, audit log (page 1) | 18 / 42 ms | 16 / 33 ms |
| Report: financial, 1 month / 1 year | 118 / 154 ms | 101 / 118 ms |
| Report: operations, 1 month / 1 year | 85 / 113 ms | 64 / 106 ms |
| Record detail (job card, customer, vehicle, invoice) | 10–23 ms | 10–20 ms |

**Concurrency:** 10 users each making 30 calls back to back with no pause (far heavier
than a workshop's staff): median 107 ms, 95th percentile 308 ms, maximum 490 ms,
no errors.

## Changes made

- **Job card search** combined three correlated `EXISTS` subqueries with `OR`, so
  PostgreSQL probed customers and vehicles once per job card. It now uses
  `IN (subquery)` scoped to the organisation, which finds matching customers and
  vehicles once.
- **Invoice list** sorted every invoice on each page load. Migration 0017 replaces
  `ix_invoices_org_status` with `ix_invoices_list (organisation_id, status, issue_date
  DESC NULLS FIRST, created_at)`, matching the list order (60 ms → under 1 ms in the
  database); it still serves date-range reports.
- **Payment list** loaded branch, customer, user, allocations and reversal links per row
  (7 queries per payment). `payments.read_many` loads them for the whole page in a fixed
  number of queries; a test checks list rows equal the detail view.

## Known limits and when to revisit

- Customer search (about 80 ms) scans contacts for phone numbers; fine at this size. Add a
  trigram index on `customer_contacts.value` if a workshop passes ~50,000 customers.
- Reports aggregate on request. If a multi-branch organisation's yearly report passes
  ~500 ms, add summary tables refreshed by the worker.
- One API process handles the pilot comfortably. For larger installations, run uvicorn
  with `--workers 2–4` (the API is stateless; sessions and rate limits live in
  PostgreSQL/Redis).
- Re-run `measure.py` before each release and after adding list screens or filters.
