# WorkshopPro development plan

This plan breaks the phases in `CLAUDE.md` §12 into shippable milestones. Each milestone ends with working API endpoints, migrations, tests, and UI — not just screens. Update the status column as work lands.

Status key: `done`, `in progress`, `next`, `planned`.

---

## Phase 0 — Repository and technical foundation — `done`

| # | Deliverable | Status |
|---|---|---|
| 0.1 | Monorepo layout: `backend/`, `frontend/`, `infrastructure/`, `docs/` | done |
| 0.2 | FastAPI app factory, settings via environment, structured JSON logging, consistent error envelope | done |
| 0.3 | SQLAlchemy 2.x engine/session, naming conventions for constraints, base model mixins (UUID PK, timestamps) | done |
| 0.4 | Alembic configured with an empty baseline migration | done |
| 0.5 | Health endpoints: `/api/v1/health/live` (process) and `/api/v1/health/ready` (database + Redis) | done |
| 0.6 | Next.js App Router + TypeScript strict + Tailwind + ESLint, design tokens from `CLAUDE.md` §9, IBM Plex fonts | done |
| 0.7 | Frontend status page that calls the API health endpoint | done |
| 0.8 | Docker Compose: postgres, redis, backend (runs migrations on start), frontend | done |
| 0.9 | Pytest + Ruff (backend), ESLint + `tsc --noEmit` (frontend), GitHub Actions CI | done |
| 0.10 | README, `.env.example`, architecture/database docs, first ADRs | done |

**Exit:** clone → copy `.env.example` → `docker compose up -d --build` → frontend on :3000 shows API and database healthy.

Deliberately deferred: Celery worker (added in Phase 3 for PDFs / Phase 5 for messaging), object storage (added in Phase 2 with photo uploads), Nginx (Phase 6), shadcn/ui components (added per screen from Phase 1).

---

## Phase 1 — Identity and organisation foundation — `next`

| # | Deliverable |
|---|---|
| 1.1 | Models + migration: organisations, organisation settings, branches, users, roles, permissions, role-permission and user-role (org- or branch-scoped) assignments, sessions, audit log |
| 1.2 | Password hashing (Argon2id), login/logout, server-side sessions in httpOnly SameSite cookies, CSRF protection (double-submit token), session expiry/revocation |
| 1.3 | Password reset with single-use, expiring, hashed tokens; rate limiting on auth endpoints (Redis) |
| 1.4 | Permission catalogue as code (`job_cards.create`, `invoices.issue`, …), seeded default roles, `require_permission()` dependency, tenant-scoped repository base |
| 1.5 | Organisation bootstrap CLI (`create-organisation` with first owner) — no public sign-up |
| 1.6 | Users & roles API + screens: invite, activate/deactivate, assign roles per branch |
| 1.7 | Branches API + screens: operating hours, service bays |
| 1.8 | Organisation settings: currency (NAD), time zone (Africa/Windhoek), date format, document numbering sequences, configurable tax rates (no default rate) |
| 1.9 | Audit log service + read-only audit screen |
| 1.10 | App shell: permission-aware sidebar, mobile navigation drawer, branch switcher, sign-in screen |
| 1.11 | Tests: cross-organisation access, permission bypass, session expiry, CSRF, rate limits |

**Exit:** an owner signs in, creates users and branches, assigns roles; the API rejects actions outside a user's permissions and organisation.

---

## Phase 2 — Core workshop operations — `planned`

First end-to-end business flow: **Customer → Vehicle → Inspection → Job Card → Mechanic Assignment**.

| # | Deliverable |
|---|---|
| 2.1 | Customers (individual/company, contacts, addresses, communication consent) |
| 2.2 | Vehicles (registration/VIN validation, ownership history, existing damage notes) |
| 2.3 | Object storage (MinIO locally, S3-compatible in production), validated uploads, image resizing, signed URLs |
| 2.4 | Job cards: org-scoped numbering (`JC-000123`), intake details, explicit state machine, status history, priority, due dates |
| 2.5 | Mechanic assignment and "my jobs" mobile view |
| 2.6 | Inspection templates (seeded default template from §3.5), mobile inspection execution with photos, draft/submit, immutable submitted record |
| 2.7 | Basic appointments and a branch/bay/mechanic day calendar |
| 2.8 | Playwright E2E for the full flow on phone and desktop viewports |

---

## Phase 3 — Commercial workflow — `planned`

Quotations with versioning, approvals bound to exact version and total, documented approval exceptions, Celery + PDF generation, invoices (immutable once issued), credit notes, payments with idempotency keys and allocations, receipts, basic operational and financial reports.

## Phase 4 — Inventory and procurement — `planned`

Parts catalogue, stock locations, stock movement ledger as source of truth, concurrency-safe reservations/issues/returns/transfers, suppliers, purchase orders, partial goods received notes, low-stock and valuation reports.

## Phase 5 — Customer experience and communications — `planned`

Customer portal with strict ownership scoping, public approval tokens, appointment requests, WhatsApp Business Platform + email adaptors behind an interface, templates, consent, delivery logs, retries, service reminders.

## Phase 6 — Production readiness and pilot — `planned`

Security and permission test sweep, query/performance review, Nginx + HTTPS, backups with tested restore, monitoring, deployment and rollback runbooks, user documentation, pilot workshop.
