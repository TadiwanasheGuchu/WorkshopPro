# Architecture overview

WorkshopPro is a **modular monolith**: one FastAPI backend, one Next.js frontend, one PostgreSQL database. See [ADR 0001](../decisions/0001-modular-monolith-and-stack.md).

## Runtime components

```text
Browser ──HTTPS──> Next.js (frontend:3000) ──HTTP──> FastAPI (backend:8000) ──> PostgreSQL
                                                         │
                                                         └────────────────────> Redis
```

- **Next.js** renders pages on the server and calls the API over the internal network (`API_INTERNAL_URL`). From Phase 1 it also forwards browser requests carrying the session cookie.
- **FastAPI** holds all business rules, authorization and transactions.
- **PostgreSQL** is the source of truth.
- **Redis** is used for rate limiting (Phase 1), and as the Celery broker when background jobs arrive (Phase 3: PDFs; Phase 5: notifications).
- **Object storage** (MinIO locally, S3-compatible in production) arrives in Phase 2 with photo uploads.
- **Nginx / managed proxy** terminates TLS in production (Phase 6).

## Backend layers

```text
api/v1/<domain>.py      thin routes: parse input, call service, shape response
  → auth dependency     who is calling (Phase 1)
  → permissions/        may they do this, in this organisation/branch (Phase 1)
services/               business rules, state machines, transactions
repositories/           tenant-scoped queries
models/                 SQLAlchemy ORM (never returned from routes)
schemas/                Pydantic request/response models
integrations/           adaptors for WhatsApp, email, storage, PDF
workers/                Celery tasks
```

Rules:
- Routes never contain business logic or raw queries.
- Services own the transaction boundary (`with db.begin(): ...`).
- Every repository query is scoped by `organisation_id`.
- Business errors are raised as `AppError` subclasses (`app/core/errors.py`) and rendered as the standard error envelope.

## Cross-cutting behaviour (implemented in Phase 0)

| Concern | Where |
|---|---|
| Settings from environment | `app/core/config.py` |
| Structured JSON logs, one line per request with request ID and duration | `app/core/logging.py`, `app/core/middleware.py` |
| `X-Request-ID` propagation (validated) | `app/core/middleware.py` |
| Security headers; HSTS in production | `app/core/middleware.py`, `frontend/next.config.ts` |
| Error envelope `{"error": {code, message, details, request_id}}` | `app/core/errors.py` |
| CORS allowlist | `CORS_ALLOWED_ORIGINS` |
| Liveness / readiness probes | `/api/v1/health/live`, `/api/v1/health/ready` |
| OpenAPI docs hidden in production | `app/main.py` |

## Frontend

- App Router with Cache Components enabled. Pages are a static shell, with request-time data streamed inside `<Suspense>`.
- Server Components by default. Server-only API access lives in `lib/api/` and is marked `server-only`.
- Design tokens in `app/globals.css` mirror `CLAUDE.md` §9. Statuses render only through `components/status-badge.tsx`.
