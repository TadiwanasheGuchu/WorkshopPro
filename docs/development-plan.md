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

Deliberately deferred: Celery worker (Phase 5 for messaging; PDFs are generated on request, see ADR 0005), object storage (added in Phase 2 with photo uploads), Nginx (Phase 6), shadcn/ui components (added per screen from Phase 1).

---

## Phase 1 — Identity and organisation foundation — `done`

| # | Deliverable | Status |
|---|---|---|
| 1.1 | Models + migration 0002: organisations, settings, tax rates, numbering, branches, hours, bays, users, roles, assignments, sessions, tokens, append-only audit log | done |
| 1.2 | Argon2id passwords, server-side sessions (HTTP-only SameSite cookie, idle + absolute expiry, revocation), CSRF double-submit bound to session | done |
| 1.3 | Password reset and invitations with single-use, expiring, hashed tokens; Redis rate limits on sign-in and reset | done |
| 1.4 | Permission catalogue as code, default role templates, `Principal.require()`, tenant-scoped lookups (404 across organisations) | done |
| 1.5 | `python -m app.cli create-organisation` installer command | done |
| 1.6 | Users & roles API and screens (invite, edit, deactivate, role assignments per branch, custom roles) | done |
| 1.7 | Branches API and screens (operating hours, service bays, archive/restore) | done |
| 1.8 | Organisation profile, preferences (NAD, Africa/Windhoek), tax rates (none seeded), document numbering | done |
| 1.9 | Audit log service and screen | done |
| 1.10 | App shell: permission-aware sidebar, mobile drawer, branch switcher, account menu; sign-in, reset and invitation pages | done |
| 1.11 | Tests: 95 backend (auth, CSRF, sessions, cross-organisation, escalation, branch scope, numbering concurrency, CLI); Playwright E2E on desktop and phone | done |
| — | nginx edge in Compose (client-IP trust boundary) and Mailpit for local email | done (pulled forward from Phase 6) |

**Exit:** met. An owner signs in, creates branches, invites users and assigns roles. The API rejects actions outside a user's permissions and organisation (see `backend/tests/test_permissions.py`).

Deferred:
- Organisation logo upload (needs object storage, Phase 2).
- Email retries (Celery, Phase 5). Until then a failed send is logged and an admin can resend the invitation.
- Session list / "sign out other devices" screen.
- Generated OpenAPI types for the frontend.

---

## Phase 2 — Core workshop operations — `done`

| # | Deliverable | Status |
|---|---|---|
| 2.1 | Customers: individual/company, multiple phones/emails, address, append-only communication consent with evidence | done |
| 2.2 | Vehicles: registration/VIN normalisation (older short chassis numbers allowed), unique per organisation, ownership history and transfer, odometer cannot drop without a reason | done |
| 2.3 | Object storage (S3 adaptor; SeaweedFS in Compose), validated uploads (decode check, size limit, EXIF/GPS stripped, resized, thumbnails), permission-checked downloads | done |
| 2.4 | Job cards: organisation-scoped numbers, explicit transition table, status history, optimistic versioning, approval rule with documented, revocable exceptions | done |
| 2.5 | Mechanic assignment (branch eligibility checked); mechanics see only assigned jobs and make workshop moves only | done |
| 2.6 | Inspection templates (default checklist seeded), mobile checklist with autosave and camera photos, submit rules, locked after submission, audited amendments, printable customer report | done |
| 2.7 | Appointments: per branch/bay/mechanic in organisation time zone, double-booking rejected, day view, check-in opens a job card | done |
| 2.8 | Playwright E2E for customer → vehicle → receive → inspect → assign, and booking → check-in, on desktop and phone | done |

**Exit:** met. Staff can register a customer and vehicle, receive the vehicle, inspect it, open a job card and assign a mechanic (`frontend/tests/e2e/workshop-flow.spec.ts`).

Deferred:
- Inspection PDF generation (Phase 3 brings server-side PDFs; a printable report exists now).
- Vehicle photos outside inspections; job card attachments.
- Mechanic leave/availability and a week view (manual day scheduling only, per CLAUDE.md §3.12).
- Upcoming appointments on the customer page (API exists: `GET /appointments/upcoming`).

---

## Phase 3 — Commercial workflow — `in progress`

| # | Deliverable | Status |
|---|---|---|
| 3a | Quotations: versions, server-calculated lines and configurable tax, send with single-use customer link, online or staff-recorded decision bound to exact version and total, revisions supersede approvals, approval unlocks repair | done |
| 3b | Invoices: drafts prefilled from the approved quotation, issue after quality inspection, number and due date from payment terms, immutable once issued (database trigger). Credit notes (full or amount, never more than remains). Payments with mandatory Idempotency-Key, locked allocations, customer credit, reversals and overpayment refunds, append-only. Customer balance. | done |
| 3c | Server-side PDFs (ReportLab, generated on request; ADR 0005): quotation (staff and customer link), invoice, credit note, receipt, inspection report with photo thumbnails | done |
| 3d | Basic reports: jobs by status, invoiced revenue vs payments received vs receivables, explicit date ranges and metric definitions | next |

Rules worth knowing:
- Invoices can be issued once the job reaches quality inspection (`INVOICEABLE` in `app/services/invoices.py`). Deposits taken earlier are recorded as unallocated payments and applied later.
- Balance due = total − credited − paid. A negative balance is an overpayment and can only be paid back as a refund against that invoice.
- A partial credit note is recorded without tax; to reverse taxed lines, credit the whole invoice and issue a corrected one. Refunding unapplied credit that is not on an invoice is not supported yet (reverse the payment instead if it was recorded in error).

## Phase 4 — Inventory and procurement — `planned`

Parts catalogue, stock locations, stock movement ledger as source of truth, concurrency-safe reservations/issues/returns/transfers, suppliers, purchase orders, partial goods received notes, low-stock and valuation reports.

## Phase 5 — Customer experience and communications — `planned`

Customer portal with strict ownership scoping, public approval tokens, appointment requests, WhatsApp Business Platform + email adaptors behind an interface, templates, consent, delivery logs, retries, service reminders.

## Phase 6 — Production readiness and pilot — `planned`

Security and permission test sweep, query/performance review, Nginx + HTTPS, backups with tested restore, monitoring, deployment and rollback runbooks, user documentation, pilot workshop.
