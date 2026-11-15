# Architecture overview

WorkshopPro is a **modular monolith**: one FastAPI backend, one Next.js frontend, one PostgreSQL database. See [ADR 0001](../decisions/0001-modular-monolith-and-stack.md).

## Runtime components

```text
                      ┌── /api/* ──────────────> FastAPI (backend:8000) ──> PostgreSQL
Browser ──> nginx ────┤                              │   │
            (edge)    └── everything else ──> Next.js (frontend:3000)   └──> Redis
                                                 │
                                                 └── server-side GETs ──> FastAPI (cookie forwarded)
FastAPI ──SMTP──> Mailpit (local) / mail server (production)
```

- **nginx** is the only published service. It routes `/api` to FastAPI and everything else to Next.js, and is the trust boundary for client IP addresses (see [ADR 0004](../decisions/0004-identity-sessions-and-permissions.md)).
- **Next.js** renders pages on the server, calling the API over the internal network (`API_INTERNAL_URL`) with the user's cookie. Client components call `/api/v1/...` on the same origin. In `next dev`, `proxy.ts` forwards `/api` instead of nginx.
- **FastAPI** holds all business rules, authorization and transactions.
- **PostgreSQL** is the source of truth.
- **Redis** holds rate-limit counters (sign-in, password reset), and becomes the Celery broker when background jobs arrive (Phase 3: PDFs; Phase 5: notifications).
- **Object storage** (MinIO locally, S3-compatible in production) arrives in Phase 2 with photo uploads.
- **Nginx / managed proxy** terminates TLS in production (Phase 6).

## Backend layers

```text
api/v1/<domain>.py      thin routes: parse input, call service, shape response
  → api/deps.py         who is calling: session cookie → Principal (+ CSRF binding)
  → permissions/        catalogue of permission codes; Principal.require(...)
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

## Authentication and authorization

See [permissions.md](permissions.md) and [ADR 0004](../decisions/0004-identity-sessions-and-permissions.md).

## Frontend

- App Router with Cache Components enabled. Pages are a static shell, with request-time data streamed inside `<Suspense>`.
- Server Components by default. Server-only API access lives in `lib/api/` and is marked `server-only`.
- Design tokens in `app/globals.css` mirror `CLAUDE.md` §9. Statuses render only through `components/status-badge.tsx`.
- `app/(auth)` holds the public sign-in, reset and invitation pages; `app/(app)` holds the signed-in area. Its layout resolves the current user (`lib/auth.ts`) inside a Suspense boundary, and every page streams its data in its own boundary.
- Server Components read through `lib/api/server.ts`. Client Components mutate through `lib/api/client.ts`, which adds the CSRF header, then call `router.refresh()`.
- Pages check the permission before fetching and render `NoAccess` when it is missing. The API enforces the same check independently.
- Forms use React Hook Form and Zod; API validation errors are mapped back onto fields (`lib/forms.ts`).
- UI primitives live in `components/ui`: Button, Field and inputs, Dialog, ConfirmButton, Panel, Pagination. They are hand-written on Radix primitives in the shadcn style, so they use our tokens directly.
