# ADR 0002 — Synchronous SQLAlchemy sessions with psycopg 3

- Status: accepted
- Date: 2026-11-15

## Context
FastAPI supports both async and sync route handlers. Async SQLAlchemy adds complexity around lazy loading, session lifecycles in background tasks, and test fixtures.

## Decision
Use synchronous SQLAlchemy 2.x sessions (`psycopg` 3 driver) and plain `def` route handlers. FastAPI runs these in its threadpool.

## Consequences
- Simpler transaction code and tests. Celery workers share the same session code.
- Throughput is bounded by threadpool size (40 by default) and the connection pool (10 + 10 overflow). This is far beyond expected per-workshop load.
- Endpoints that call slow external services (WhatsApp, email) must not do so inline; they enqueue background jobs instead, which CLAUDE.md requires anyway.
- If a future need for high-concurrency I/O appears, individual routes can become `async` without changing the data layer.
