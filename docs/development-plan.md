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
- Inspection PDF generation (done in Phase 3c).
- Vehicle photos outside inspections; job card attachments.
- Mechanic leave/availability and a week view (manual day scheduling only, per CLAUDE.md §3.12).
- Upcoming appointments on the customer page (API exists: `GET /appointments/upcoming`).

---

## Phase 3 — Commercial workflow — `done`

| # | Deliverable | Status |
|---|---|---|
| 3a | Quotations: versions, server-calculated lines and configurable tax, send with single-use customer link, online or staff-recorded decision bound to exact version and total, revisions supersede approvals, approval unlocks repair | done |
| 3b | Invoices: drafts prefilled from the approved quotation, issue after quality inspection, number and due date from payment terms, immutable once issued (database trigger). Credit notes (full or amount, never more than remains). Payments with mandatory Idempotency-Key, locked allocations, customer credit, reversals and overpayment refunds, append-only. Customer balance. | done |
| 3c | Server-side PDFs (ReportLab, generated on request; ADR 0005): quotation (staff and customer link), invoice, credit note, receipt, inspection report with photo thumbnails | done |
| 3d | Reports with explicit inclusive periods in the organisation time zone, branch-scoped: financial (invoiced, credited, received, refunded, reversed, by method and day; receivables and ageing as at today; unapplied credit) and operations (received, completed, cancelled, turnaround, open now, quotation outcomes, mechanic workload). Metric definitions returned with each report and shown on screen. New permissions `reports.financial` and `reports.operational` (migration 0009). | done |

**Exit:** met. A job is quoted, approved, completed, invoiced and paid partially or fully, with correct balances, receipts, PDFs and audit history (`backend/tests/test_invoices.py`, `frontend/tests/e2e/invoice.spec.ts`).

Rules worth knowing:
- Invoices can be issued once the job reaches quality inspection (`INVOICEABLE` in `app/services/invoices.py`). Deposits taken earlier are recorded as unallocated payments and applied later.
- Balance due = total − credited − paid. A negative balance is an overpayment and can only be paid back as a refund against that invoice.
- A partial credit note is recorded without tax; to reverse taxed lines, credit the whole invoice and issue a corrected one. Refunding unapplied credit that is not on an invoice is not supported yet (reverse the payment instead if it was recorded in error).

## Phase 4 — Inventory and procurement — `done`

| # | Deliverable | Status |
|---|---|---|
| 4a | Parts catalogue (categories, units, cost and selling price, tax), stock locations per branch (default store created with every branch), append-only stock movement ledger maintained by database trigger, opening stock and stocktake adjustments with mandatory reason, transfers of available stock, minimum levels and low-stock filter, movement ledger screen. Every stock-changing request needs an Idempotency-Key. | done |
| 4b | Reserve stock for authorised jobs (approved quotation or approval exception), issue parts when fitted (drawing on the job's reservations first), returns limited to what was issued, manual release, automatic release when a job is completed or cancelled; Parts panel on the job card | done |
| 4c | Suppliers with their part codes, prices and lead times; purchase orders (draft, approved, partly received, received, closed short, cancelled) with approval; goods received notes for partial deliveries with delivery-note and supplier-invoice references and discrepancy notes; returns to supplier; purchase order PDF | done |
| 4d | Inventory report (permission `reports.inventory`, migration 0013): stock value at cost by location and category as at today, low-stock count, movements by type with cost value, most-used parts, purchasing (approved, received, returned, still on order, overdue), and a stock check comparing every stock level with its ledger and open reservations | done |

**Exit:** met. A workshop orders parts from a supplier, receives partial and full deliveries into stock, reserves and issues parts to authorised jobs, returns parts, and the stock check confirms every stock level matches the movement ledger (`backend/tests/test_purchasing.py`, `test_job_parts.py`, `test_reports.py::test_inventory_report`; Playwright `purchasing.spec.ts`, `job-parts.spec.ts`).

Rules worth knowing:
- `stock_movements` is the source of truth. `stock_levels.on_hand` changes only through the movement trigger (`stock_movement_apply`); direct updates, deletes and edits to movements are rejected by the database.
- Stock cannot go below zero, or below what is reserved for jobs. Transfers move only available (unreserved) stock.
- Operations lock the affected stock-level rows in a fixed order, so concurrent requests cannot oversell (`test_concurrent_removals_cannot_oversell`).
- The parts catalogue is organisation-wide: managing it (`inventory.catalogue`) needs an organisation-wide role. Stock is per branch.
- Cost prices are shown only to users who manage the catalogue or adjust stock.
- `stock_levels.reserved` equals the outstanding total of open `stock_reservations` for the part and location; the tests assert this. Parts must come from a location in the job's branch.
- Receiving never exceeds what is outstanding on the order line. Each delivery adds stock through the ledger at the order line's cost, and sets the part's cost price and the supplier's last cost to that cost (stock is valued at cost price, which therefore follows the last received cost).
- Returns to supplier are limited to what was received on the line, net of earlier returns, and to free stock at the chosen location.
- Purchase order amounts exclude tax. Supplier payments and balances owed to suppliers are not recorded (WorkshopPro is not a general ledger); GRNs keep the supplier's invoice reference for reconciliation in the accounting system.
- Issued parts are not added to invoices automatically yet: the invoice is prefilled from the approved quotation, and the Parts panel shows what was fitted so staff can reconcile before issuing.

## Phase 5 — Customer experience and communications — `done`

| # | Deliverable | Status |
|---|---|---|
| 5a | Notifications (ADR 0006): Celery worker in Compose, WhatsApp Business Platform and email behind adaptors, consent-based channel choice, per-event templates with restricted placeholders, delivery log with provider reference and failure reason, retries with backoff, periodic sweep, signed delivery-status webhook, Notifications screen and templates. Events: vehicle received, quotation ready (link never stored), ready for collection, invoice issued. | done |
| 5b | Customer portal: portal accounts separate from staff (own session cookie), sign-in by single-use emailed link (15 min, hashes only, no account enumeration, rate limited), every query scoped to the signed-in customer; vehicles, job progress, service history, quotation approve/decline (`customer_portal` decision method), invoices, receipts and inspection PDFs, phone/preferred contact/consent updates; staff invite, resend and remove access from the customer page (migration 0015) | done |
| 5c | Booking requests from the portal (own vehicles, active branches, morning/afternoon/any, limit of five waiting, cancel while pending); staff confirm into a booking with the normal conflict rules or decline with a reason, and the customer is notified. Service reminders: next-service due date and km per vehicle, reminder days setting (default 14), hourly worker job, one reminder per vehicle and due date (migration 0016). | done |

**Exit:** met. A customer signs in to the portal by emailed link and sees only their own records, approves a quotation, requests a booking that the workshop confirms, and receives traceable notifications whose delivery, failures and retries are logged (`backend/tests/test_portal.py`, `test_notifications.py`, `test_appointment_requests.py`; Playwright `portal.spec.ts`, `notifications.spec.ts`).

## Phase 6 — Production readiness and pilot — `in progress`

| # | Deliverable | Status |
|---|---|---|
| 6.1 | Security sweep generated from the OpenAPI document: every operation rejects anonymous callers unless on a reviewed public list; portal and staff sessions cannot reach each other's endpoints; security headers | done |
| 6.2 | Production configuration guard: the API refuses to start in production with HTTP base URL, localhost/wildcard CORS, insecure cookies, placeholder secrets, Mailpit/local SMTP, log-only WhatsApp, or rate limits off | done |
| 6.3 | Content-Security-Policy on app pages in production builds (no violations across staff and portal pages) | done |
| 6.4 | Dependency scan: `pip-audit` (Python) and `npm audit --omit=dev` (frontend) — no known vulnerabilities on 2026-11-17 | done |
| 6.5 | Backups: snapshot-consistent `pg_dump` + object storage export with manifest and checksums, retention; restore with verification (row counts, stock ledger, reservations, invoice balances, stored files); restore drill into a throwaway Compose project — run and passed (`docs/deployment/backups.md`) | done |
| 6.6 | HTTPS for Compose, monitoring and health checks, deployment/upgrade/rollback runbooks | next |
| 6.7 | Query/performance review, staff user guide and onboarding | planned |
| 6.8 | Pilot workshop: server and domain, real SMTP, approved WhatsApp templates, tax settings confirmed with an adviser | needs owner input |

Release checklist (repeat before every release):

```bash
cd backend && uv run --with pip-audit pip-audit --strict
cd frontend && npm audit --omit=dev
cd backend && uv run pytest -q   # includes tests/test_security_sweep.py
```
