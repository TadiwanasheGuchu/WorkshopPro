# WorkshopPro — Claude Code Project Instructions

> **Purpose:** Build WorkshopPro, a production-minded automotive workshop management platform for garages and service centres in Namibia.
>
> **Primary market:** Independent garages, medium-sized workshops, and multi-branch automotive service centres.
>
> **Commercial model:** Once-off installation with a separately defined maintenance agreement.
>
> **Default currency:** Namibian Dollar (NAD / N$).
>
> **Product form:** Responsive web application for desktop, tablet, and mobile.

This file is the project-wide source of truth for Claude Code. Read it before making changes. Follow the product rules, architecture, security requirements, and implementation sequence below. If a requirement is unclear, inspect the existing code and documentation first. Ask a focused question only when a consequential product or security decision cannot safely be inferred.

---

## 1. Product vision

WorkshopPro manages the complete lifecycle of a vehicle repair:

1. Customer and vehicle are registered.
2. Vehicle is received and mileage/condition are recorded.
3. A vehicle inspection is completed, with notes and photos.
4. A job card is created and assigned.
5. The workshop diagnoses the problem.
6. A quotation is prepared and sent to the customer.
7. The customer approves or rejects the exact quotation version.
8. Required parts are reserved and issued.
9. Mechanics complete the repair and record work performed.
10. A quality inspection is completed.
11. An invoice is issued and payments are recorded.
12. The vehicle is handed over and its service history is updated.

The application must make this workflow traceable. Staff should always be able to answer:
- What is happening to this vehicle?
- Who is responsible for the next action?
- Has the customer approved the work?
- Are the required parts available?
- What has been charged and what has been paid?
- What has been communicated to the customer?

### Product principles

- Build for real workshop operations, not a generic CRM or admin template.
- Keep common tasks fast and obvious.
- Make job status, ownership, approvals, and outstanding actions visible.
- Maintain a reliable audit trail for operational and financial actions.
- Use mobile-first workflows for mechanics and inspections.
- Support one-branch workshops without making multi-branch support an afterthought.
- Prefer clear, maintainable engineering over unnecessary complexity.
- Do not claim to be a complete accounting package.

---

## 2. Target users and roles

Support organisation-level and branch-level access.

Initial role suggestions (permissions must be configurable):
- **Owner / Organisation Admin:** all organisation settings, branches, users, reports, and records.
- **Workshop Manager:** job workflow, assignments, inspections, quotations, scheduling, and operational reports.
- **Service Advisor / Receptionist:** customers, vehicles, bookings, job intake, quotations, customer communication, and handover.
- **Mechanic / Technician:** assigned jobs, diagnosis, task updates, parts requests, inspections, and repair notes.
- **Inventory Manager:** parts catalogue, stock movements, suppliers, purchase orders, and goods received.
- **Accounts / Cashier:** quotations where permitted, invoices, payments, receipts, credit notes, and finance reports.
- **Customer:** restricted self-service portal access to their own vehicles and authorised records.

Do not rely on role names alone for authorization. Implement permission checks on the backend for every protected operation. The frontend may hide unavailable actions for usability, but frontend visibility is never a security boundary.

---

## 3. Scope and modules

Build the system as a modular monolith with clear domain boundaries.

### 3.1 Authentication and organisation setup
- Secure sign-in, sign-out, password reset, and session management.
- Organisation profile, logo, contact information, and document details.
- Branches, operating hours, service bays, and branch settings.
- User invitations, activation/deactivation, roles, and permissions.
- Organisation preferences: currency, configurable tax settings, time zone, date format, and document numbering.
- Audit events for security-sensitive and business-critical actions.

### 3.2 Customers
- Individual and company customer profiles.
- Multiple phone numbers, email addresses, and physical/postal addresses where needed.
- Customer communication preferences and consent.
- Multiple vehicles per customer.
- Customer job, quotation, invoice, payment, and service history.
- Outstanding balance summary based on issued invoices and allocated payments.

### 3.3 Vehicles
Capture fields where available:
- Registration number.
- Make, model, variant, and year.
- VIN/chassis number and engine number.
- Fuel type, transmission, colour, and mileage/odometer.
- Customer/owner relationship.
- Vehicle photos and existing-damage notes.
- Service and repair history.

Allow optional fields where information is not available. Validate registration/VIN sensibly without assuming every vehicle has complete data.

### 3.4 Job cards
A job card is the central operational record.

Include:
- Unique job number scoped to the organisation.
- Branch, customer, and vehicle.
- Customer complaint and requested work.
- Intake mileage, fuel level if captured, received date/time, and expected completion.
- Diagnosis, labour tasks, parts, notes, photos, and attachments.
- Assigned mechanic(s), priority, and due date.
- Linked inspection(s), quotation versions, approvals, stock movements, invoice, and payment status.
- Status history with actor and timestamp.
- Vehicle collection/handover information.

Suggested workflow statuses:
- Vehicle received
- Inspection pending
- Diagnosis in progress
- Awaiting quotation approval
- Awaiting parts
- Repair in progress
- Quality inspection
- Ready for collection
- Completed / collected
- Cancelled

Use explicit, validated state transitions in the backend. Do not let clients submit arbitrary status strings. Record every transition in job status history.

**Approval rule:** Work that incurs customer charges must not begin until the relevant quotation has been approved, unless an authorised user records a documented exception. Record who authorised the exception, when, why, and what scope it covers.

### 3.5 Vehicle inspections
Provide configurable inspection templates with sections such as:
- Exterior and bodywork
- Windows and mirrors
- Tyres and wheels
- Brakes
- Steering and suspension
- Engine and visible leaks
- Battery and electrical
- Lights and indicators
- Interior and safety equipment
- Fluids
- Odometer and dashboard warnings
- Existing damage

Each item should support:
- Pass
- Attention required
- Failed
- Not inspected
- Notes
- Optional photo evidence

Allow staff to create an inspection from a template, save drafts, submit/complete it, and generate a customer-readable PDF. Preserve the submitted inspection as a historical record; edits after submission must be controlled and audited.

### 3.6 Quotations and approvals
- Build quotations from labour, parts, fees, discounts, and configurable taxes.
- Support quotation expiry, terms, notes, and versioning.
- Generate a branded PDF.
- Send through supported email or WhatsApp integrations.
- Record sent, viewed where technically supported, approved, rejected, and expired states.
- Customer approval must be linked to the exact quotation version and total.
- Capture approval timestamp, method, customer identity/evidence, and any comments.
- Changes to an approved quotation must create a new version and require approval again when the scope or price changes.

Never treat opening a link as approval.

### 3.7 Inventory and parts
- Parts catalogue with SKU, name, description, category, supplier references, cost, selling price, and tax treatment where applicable.
- Stock by branch/location.
- Minimum stock thresholds and low-stock alerts.
- Stock adjustments with mandatory reason and audit event.
- Stock transfers between locations.
- Reservations against authorised jobs.
- Issue/consume parts when they are actually issued or fitted, not merely when quoted.
- Returns to stock and supplier returns.
- Stock movement ledger and stock valuation reports.

**Inventory integrity:** Treat the stock movement ledger as the source of truth. Do not rely only on directly editing a `quantity` field. Use database transactions and concurrency-safe updates for reservations, issues, returns, and transfers. Prevent negative stock unless an explicitly configured and permission-controlled exception exists.

### 3.8 Suppliers and purchasing
- Supplier profiles and contacts.
- Supplier part references and purchase history.
- Purchase orders with line items, costs, expected delivery, and approval state.
- Goods received notes supporting partial deliveries.
- Record supplier invoice references and outstanding balances.
- Returns and discrepancies.
- Maintain links from purchase orders and goods received notes to stock movements.

### 3.9 Invoices and payments
- Generate invoices from completed/approved job work.
- Include labour, parts, discounts, configurable taxes, deposits, and adjustments.
- Support cash, EFT/bank transfer, card (record-only initially), and other configured payment methods.
- Support partial payments and payment allocations.
- Generate receipts and downloadable PDFs.
- Show invoice totals, amounts paid, and outstanding balances.
- Support credit notes and controlled refunds/adjustments.

**Financial integrity rules:**
- Use PostgreSQL `NUMERIC(14,2)` or an appropriately sized fixed-precision numeric type for money. Never use floating-point values for monetary calculations.
- Store currency code on financial documents; default to NAD.
- Issued invoices are immutable. Correct them with credit notes or controlled adjustment records.
- Prevent duplicate payment submission with idempotency protection.
- Record payment allocation and balance changes transactionally.
- Initially record payments; do not implement card acquiring or payment processing unless separately specified.
- Distinguish revenue, cash received, receivables, and expenses in reports.
- Tax rules must be configurable and verified with a qualified Namibian accounting/tax adviser. Do not hardcode an assumed tax rate.

This is workshop invoicing and payment tracking, not a full general ledger or accounting suite.

### 3.10 WhatsApp and notifications
Plan integration with the official WhatsApp Business Platform or an approved provider. Do not automate personal WhatsApp Web sessions.

Potential customer notifications:
- Vehicle received.
- Inspection completed.
- Quotation ready.
- Quotation approved/rejected.
- Repair started.
- Parts delayed.
- Vehicle ready for collection.
- Service reminder.

Requirements:
- Store customer communication consent and opt-in evidence.
- Use approved message templates where required by the provider.
- Store message status, provider reference, timestamps, and failure reason.
- Implement retry and failure handling through background jobs.
- Never expose provider credentials to the browser.
- Keep notification sending asynchronous; the main job workflow must remain usable if a provider is unavailable.

### 3.11 Customer self-service portal
Customers may:
- View their own registered vehicles.
- Submit appointment requests.
- View authorised job progress.
- View and approve/reject quotations.
- View invoices and receipts.
- Review service history.
- Send enquiries and update permitted contact details.

Strictly scope every portal request to the authenticated customer account and organisation. Never trust a customer ID supplied by the browser without verifying ownership and access. Public approval links must be random, expiring, single-purpose, and limited to the exact quotation/action. Do not use sequential database IDs in public links.

### 3.12 Scheduling and workforce
- Appointment requests and confirmed bookings.
- Workshop calendar by branch, bay, and mechanic.
- Mechanic availability, leave, and working hours.
- Job assignment and estimated duration.
- Overdue and workload indicators.
- Support multiple branches and service bays.

Avoid complex optimisation in the first release. Provide reliable manual scheduling first.

### 3.13 Dashboard and reporting
Show useful operational summaries:
- Jobs received today.
- Jobs in progress.
- Jobs awaiting diagnosis, approval, or parts.
- Vehicles ready for collection.
- Overdue jobs.
- Daily/monthly invoiced revenue.
- Payments received.
- Outstanding receivables.
- Low-stock parts and stock valuation.
- Mechanic workload.
- Parts usage and supplier purchasing.

All reports must respect organisation, branch, and user permissions. Make date ranges explicit. Explain metric definitions and do not label invoices issued as cash received.

---

## 4. Technology stack

Use this stack unless the project already contains a deliberate, documented alternative:

### Frontend
- Next.js (App Router) and TypeScript.
- Tailwind CSS.
- shadcn/ui and Radix primitives.
- Lucide icons.
- React Hook Form and Zod for form handling and validation.
- TanStack Table where advanced data tables are needed.
- Use server components by default; use client components only where interaction requires them.

### Backend
- Python 3.12+.
- FastAPI.
- Pydantic.
- SQLAlchemy 2.x.
- Alembic migrations.
- Explicit service and repository boundaries where they improve maintainability.

### Data and infrastructure
- PostgreSQL as the source of truth.
- Redis for queues/cache where needed.
- Celery (or a clearly justified alternative) for background work.
- S3-compatible object storage or a compatible storage service for photos and documents.
- Docker Compose for local development and initial deployments.
- Nginx or a managed reverse proxy for production routing.

### Quality
- Pytest for backend tests.
- Playwright for critical end-to-end flows.
- Ruff for Python linting/formatting.
- TypeScript strict mode and ESLint.
- OpenAPI documentation generated by FastAPI.

Do not add microservices, Kubernetes, event streaming, or additional infrastructure without a real requirement. Start with a modular monolith.

---

## 5. Architecture and project structure

Keep business logic out of route handlers and UI components.

Backend request flow:

`API route → authentication → permission check → service → repository/data access → PostgreSQL`

Suggested repository structure (adapt to the actual repository rather than moving files unnecessarily):

```text
workshoppro/
├── CLAUDE.md
├── README.md
├── .env.example
├── docker-compose.yml
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── (dashboard)/
│   │   │   ├── overview/
│   │   │   ├── customers/
│   │   │   ├── vehicles/
│   │   │   ├── job-cards/
│   │   │   ├── inspections/
│   │   │   ├── quotations/
│   │   │   ├── inventory/
│   │   │   ├── suppliers/
│   │   │   ├── purchases/
│   │   │   ├── invoices/
│   │   │   ├── payments/
│   │   │   ├── scheduling/
│   │   │   ├── reports/
│   │   │   └── settings/
│   │   └── portal/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── tests/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── permissions/
│   │   ├── integrations/
│   │   ├── workers/
│   │   └── reports/
│   ├── migrations/
│   └── tests/
├── infrastructure/
│   ├── docker/
│   ├── nginx/
│   ├── backups/
│   └── monitoring/
└── docs/
    ├── architecture/
    ├── api/
    ├── database/
    ├── deployment/
    └── decisions/
```

Use feature/domain-oriented modules. Avoid enormous files and circular dependencies. Keep API schemas separate from ORM models. Do not return ORM objects directly from API routes.

---

## 6. Database design rules

Core entities will include:

- Organisations, branches, organisation settings.
- Users, roles, permissions, user-role assignments, sessions.
- Customers and customer contacts.
- Vehicles and vehicle ownership/history.
- Job cards, job tasks, job assignments, job status history.
- Inspection templates, template items, inspections, inspection results.
- Quotations, quotation items, quotation versions, quotation approvals.
- Parts, categories, stock locations, stock movements, reservations.
- Suppliers, supplier parts, purchase orders, purchase order items, goods received notes.
- Invoices, invoice items, credit notes.
- Payments and payment allocations.
- Appointments, service bays, mechanic availability.
- Notification logs, message templates, customer consents.
- Customer portal accounts/access tokens.
- Audit logs.

### Mandatory database rules
1. Every organisation-owned record must carry `organisation_id`. Add `branch_id` where the record belongs to a branch.
2. Enforce tenant scope in service/repository queries and authorization checks.
3. Add foreign keys, indexes, unique constraints, and check constraints deliberately.
4. Use UUID primary keys for externally exposed records unless a documented reason suggests otherwise.
5. Use `TIMESTAMPTZ` for timestamps and store/interpret times consistently.
6. Use fixed-precision numeric types for money.
7. Use unique constraints for organisation-scoped job, quotation, and invoice numbers.
8. Use soft archive/deactivation for important business records; do not cascade-delete financial or audit history.
9. Use database transactions for multi-step business operations.
10. Add indexes for common filters: organisation, branch, status, dates, customer, vehicle, and document numbers.
11. Never rely on frontend validation for data integrity.
12. Create schema changes through Alembic migrations; do not manually alter production databases.

For hosted multi-tenant deployments, PostgreSQL Row-Level Security may be added as defence in depth. It does not replace application-level permission checks.

---

## 7. API conventions

Use a versioned API prefix: `/api/v1`.

Suggested resource endpoints:
- `/auth`
- `/users`
- `/organisations`
- `/branches`
- `/customers`
- `/vehicles`
- `/job-cards`
- `/inspections`
- `/quotations`
- `/inventory/parts`
- `/inventory/movements`
- `/suppliers`
- `/purchase-orders`
- `/invoices`
- `/payments`
- `/appointments`
- `/notifications`
- `/reports`
- `/portal`

Use resource-oriented endpoints for normal CRUD, and explicit action endpoints for state transitions, for example:
- `POST /job-cards/{id}/assignments`
- `POST /inspections/{id}/submit`
- `POST /quotations/{id}/send`
- `POST /quotations/{id}/approve`
- `POST /job-cards/{id}/start`
- `POST /job-cards/{id}/complete`
- `POST /invoices/{id}/issue`
- `POST /payments`
- `POST /purchase-orders/{id}/receive`

API standards:
- Validate request and response schemas.
- Use consistent error response structures and correct HTTP status codes.
- Paginate list endpoints.
- Support filtering and sorting through validated parameters.
- Never expose secrets, internal stack traces, or unrestricted ORM fields.
- Enforce authentication, tenant scope, and permissions on every protected endpoint.
- Use idempotency keys for payment and stock-changing operations where duplicate requests could cause harm.
- Document non-obvious API behaviour in OpenAPI descriptions.

---

## 8. Security requirements

Treat customer, vehicle, business, and financial information as sensitive business data.

- Hash passwords with Argon2id or a current, appropriately configured password hashing scheme.
- Use secure, HTTP-only, SameSite cookies for browser sessions where applicable.
- Protect state-changing cookie-authenticated requests against CSRF.
- Enforce HTTPS in production.
- Rate-limit authentication, password reset, public approval, and other abuse-prone endpoints.
- Validate and authorise uploads; restrict file types, size, and storage access.
- Store secrets in environment variables or a secrets manager, never in source control.
- Provide `.env.example` with placeholders only.
- Apply organisation/branch scoping on the server.
- Log security-sensitive actions without logging passwords, tokens, or unnecessary personal data.
- Add audit logs for approvals, financial changes, stock adjustments, permission changes, and important status transitions.
- Use expiring, revocable sessions and reset tokens.
- Use random, expiring, single-purpose public tokens.
- Add secure headers and a production CORS allowlist.
- Back up databases and files; document and test restoration.
- Scan dependencies and container images as part of release preparation.

Never claim a feature is secure merely because it is hidden in the UI. Add tests for cross-organisation access and permission bypass attempts.

---

## 9. UI and visual design direction

### Design identity
WorkshopPro should feel like a premium, practical automotive operations product. Avoid generic AI-generated dashboard styling.

### Colour palette
- Deep slate: `#202A34` — navigation, headings, body text, text on orange.
- Steel blue: `#30485B` — secondary structure, links, selected states.
- Signal orange: `#F07C1F` — primary action fill only (hover `#E06A0C`).
- Mist background: `#F3F5F6` — app background behind work areas.
- White surface: `#FFFFFF` — tables, panels, forms.
- Border: `#DDE2E6`. Muted text: `#5B6670`.

Use a light theme by default. Use deep slate for navigation and strong structural elements, signal orange for the single primary action on a screen, and neutral backgrounds for work areas.

**Orange rules:** Orange is a fill, never a text colour. Text on an orange fill is deep slate (`#202A34`, 5.3:1). White on orange fails WCAG AA and is not allowed. Do not use orange for statuses — orange means "action", not "state". The earlier amber `#D97732` was retired because it reads as brown.

### Status colours
Statuses use a fixed set of five families. A badge is a pale tint background, a solid colour dot, and **deep slate text** (never coloured text — tinted text on tints drifts into brown/olive and fails contrast). The label text carries the meaning; colour reinforces it.

| Family | Dot | Tint | Used for |
|---|---|---|---|
| Neutral | `#64748B` | `#EEF1F4` | Vehicle received, Inspection pending, Draft, Not inspected, Cancelled, Completed/collected |
| Active (blue) | `#2563EB` | `#E6EEFC` | Diagnosis in progress, Repair in progress, Quality inspection, Sent |
| Waiting (yellow) | `#EAB308` | `#FDF6D8` | Awaiting quotation approval, Awaiting parts, Attention required, Partially paid |
| Success (green) | `#16A34A` | `#E3F5E9` | Ready for collection, Approved, Pass, Paid |
| Danger (red) | `#DC2626` | `#FBE7E7` | Overdue, Failed, Rejected, Expired, Payment failed, Low stock |

Define these once as design tokens and a single `StatusBadge` component; screens must not invent their own status colours.

### Visual anti-patterns (do not use)
WorkshopPro must not look like a generic AI-generated dashboard. Avoid:

**Colour and surface**
- Brown, beige, tan, cream, or "warm paper" tones anywhere.
- Purple, violet, or indigo accents.
- Gradients of any kind — backgrounds, buttons, text, borders, glows.
- Glassmorphism, frosted/blurred panels, translucent overlays.
- Large, soft, or coloured drop shadows. Use a 1px border; at most one subtle shadow level for popovers/dialogs.
- Pastel tints on every card. Surfaces are white on mist.
- Neon, "hacker" dark themes.

**Icons and decoration**
- Emoji anywhere in the product UI (headings, buttons, toasts, empty states).
- Sparkle/magic-wand icons or anything implying AI where there is none.
- An icon in a rounded coloured square beside every heading or metric.
- Mixed icon sets, sizes, or stroke widths. Lucide only, 16px inline / 20px nav, default stroke.
- Decorative blobs, waves, dot grids, abstract 3D shapes, isometric or stock illustrations.

**Layout**
- A row of large KPI cards with icons and green "+12%" pills. Use a compact strip of actionable counts (overdue, awaiting approval, ready for collection) that link to filtered lists.
- Cards inside cards; wrapping every section in a card. Prefer plain sections, dividers, and tables.
- Over-rounded corners. Radius: 6px controls/badges, 8px panels/dialogs.
- Oversized padding and whitespace. Favour practical density.
- Hero sections, welcome banners, "Good morning, John".
- Centred content on working screens. Left-align.
- Bento-grid dashboards and decorative charts without axes or meaning.

**Typography and copy**
- Gradient or highlighted words in headings; a grey subtitle under every title.
- Marketing language inside the app: "supercharge", "seamless", "effortless", "unlock", "elevate", "all-in-one", "streamline".
- Exclamation marks and cheerleading ("Great job!", "You're all set!").
- Vague labels ("Insights", "Analytics hub"). Use workshop terms: Job Cards, Awaiting Parts, Ready for Collection.
- Title Case On Every Label. Use sentence case.

**Motion and interaction**
- Entrance animations, staggered card reveals, hover lift/scale on cards, animated number counters.
- Pulsing or shimmering elements used as decoration (skeletons are fine for real loading states).
- Toasts for trivial actions.

**Data and content**
- Fake-realistic placeholder data ("John Doe", "Acme Corp", round revenue figures) on production screens.
- Stock-photo avatars. Use initials.
- Ad-hoc pastel badge colours. Use the status families above.
- Unrequested "AI-powered" features (chatbots, smart suggestions, AI summaries).

**Reference quality bar:** Linear, Stripe Dashboard, and well-built fleet/ERP software — flat surfaces, thin borders, dense readable tables, one accent used sparingly, colour reserved for status, and every screen organised around what needs doing next.

### Typography
- Font: IBM Plex Sans (UI) and IBM Plex Mono (job numbers, registration numbers, SKUs, amounts in tables). Self-host via `next/font`.
- Base size 14px on desktop, 16px for form inputs on mobile (prevents iOS zoom).
- Tabular numerals for money and quantities; right-align amounts in tables.
- Format money as `N$ 1,234.50`.

### UI rules
- Follow the visual anti-patterns list above.
- Use a clear typographic hierarchy and consistent spacing.
- Make tables readable and useful, with search, filters, pagination, and clear empty states.
- Use badges for actual statuses, not decoration.
- Provide loading, error, empty, success, and disabled states.
- Confirm destructive actions.
- Use accessible labels, keyboard navigation, visible focus states, and adequate contrast.
- Prefer practical density over oversized cards.
- Avoid displaying every metric as a large card. Prioritise what a workshop employee needs to act on.

### Navigation
Use a permission-aware sidebar with groups similar to:

```text
WORKSHOPPRO

OVERVIEW
  Dashboard

WORKSHOP
  Job Cards
  Inspections
  Appointments
  Workshop Calendar
  Mechanics

CUSTOMERS
  Customers
  Vehicles

INVENTORY
  Parts Catalogue
  Stock Movements
  Suppliers
  Purchase Orders

FINANCE
  Quotations
  Invoices
  Payments

CUSTOMER EXPERIENCE
  Customer Portal
  Notifications

ANALYTICS
  Reports

ADMINISTRATION
  Users & Roles
  Branches
  Settings
  Audit Logs
```

Do not show navigation items the signed-in user cannot access.

### Mobile-first requirements
Mechanics and inspectors will often use phones in the workshop:
- Design phone layouts first for job tasks, inspections, photos, and status updates.
- Use large touch targets and clear actions.
- Minimise typing with sensible defaults, dropdowns, checklists, and saved values.
- Make photo capture/upload straightforward.
- Avoid wide tables on phones; use stacked record summaries or responsive table alternatives.
- Preserve unsent form input when practical.
- Paginate and compress images; keep screens usable on slower connections.
- Make important job details and next actions easy to find.
- Tablet and desktop layouts should expand naturally for reception, management, and inventory workflows.

Do not promise full offline support in the first release. Offline-first operation requires a separately designed synchronisation and conflict-resolution strategy.

---

## 10. Commercial and deployment model

The initial commercial model is a once-off installation fee plus a maintenance agreement. Do not design the product around mandatory monthly SaaS billing.

Support two deployment approaches:

### Preferred initial approach: managed dedicated installation
- Dedicated environment for each customer or a clearly isolated deployment model.
- Application, database, object storage, HTTPS, backups, monitoring, and controlled remote maintenance.
- Customer-specific domain/subdomain where appropriate.
- Document ownership, access, data export, backup retention, and exit procedures.

### Alternative: customer-owned on-premises installation
- Docker Compose deployment on customer-managed hardware/server.
- Local network access where appropriate.
- Secure remote access only when deliberately configured.
- Document update, backup, restore, and support responsibilities.

Start with Docker Compose. Do not introduce Kubernetes for the initial product.

Maintenance agreements must define exactly what is included: backups, security updates, bug fixes, support response expectations, uptime monitoring, and minor improvements. Custom features, integrations, data migration, and major upgrades should be separately scoped and quoted.

---

## 11. Non-functional requirements

- Responsive on current Chrome, Edge, Firefox, and Safari.
- Target 99.5% monthly availability for managed production installations, subject to hosting and maintenance arrangements.
- Typical API response target below 500 ms for ordinary operations under expected pilot load; measure rather than promise.
- Daily automated database backups and a documented restore process.
- Periodic restore tests.
- WCAG 2.2 AA as the accessibility target.
- Paginated data access and efficient queries.
- Compressed/resized images and controlled upload sizes.
- Structured application logs and basic health checks.
- Clear deployment and rollback instructions.

---

## 12. Development phases

Implement in controlled, testable phases. Do not try to generate the entire platform in one pass.

### Phase 0 — Repository and technical foundation
- Inspect the existing repository and report its current state.
- Confirm installed runtime versions and project conventions.
- Set up frontend, backend, Docker Compose, PostgreSQL, and environment configuration.
- Add health checks, linting, formatting, and test scaffolding.
- Create initial architecture and database documentation.
- Ensure a clean local startup process.

**Exit criteria:** A developer can clone the repository, configure environment variables, start the stack, and access the frontend and API health endpoint.

### Phase 1 — Identity and organisation foundation
- Authentication and session handling.
- Organisation and branch setup.
- Users, roles, and permission checks.
- Dashboard shell and responsive navigation.
- Audit logging foundation.

**Exit criteria:** An organisation admin can sign in, create/manage users and branches, and permissions are enforced by the API.

### Phase 2 — Core workshop operations
- Customer management.
- Vehicle management.
- Job card creation and status workflow.
- Mechanic assignment.
- Inspection templates and inspection execution.
- Basic appointment/scheduling support.

**Exit criteria:** Staff can register a customer and vehicle, receive the vehicle, inspect it, create a job card, and assign a mechanic.

### Phase 3 — Commercial workflow
- Quotations and quotation versioning.
- Customer approvals.
- PDF generation.
- Invoices and receipts.
- Payment recording and allocation.
- Basic operational and financial reports.

**Exit criteria:** A job can be quoted, approved, completed, invoiced, and paid partially or fully with correct balances and audit history.

### Phase 4 — Inventory and procurement
- Parts catalogue and stock locations.
- Stock movement ledger and reservations.
- Suppliers and purchase orders.
- Goods received notes and partial delivery handling.
- Low-stock reporting.

**Exit criteria:** A workshop can order parts, receive them into stock, reserve and issue parts to jobs, and reconcile stock movements.

### Phase 5 — Customer experience and communications
- Customer portal.
- Appointment requests.
- WhatsApp/email integration.
- Notification templates, consent, logs, retries, and service reminders.

**Exit criteria:** A customer can securely access their own authorised records and receive traceable notifications.

### Phase 6 — Production readiness and pilot
- Security and permission testing.
- Performance and query review.
- Backup and restore verification.
- Deployment automation and monitoring.
- User documentation and staff onboarding.
- Pilot workshop feedback and fixes.

**Exit criteria:** A pilot customer can use the system for real jobs with documented support, recovery, and operational procedures.

---

## 13. Testing and acceptance criteria

Write tests as each feature is implemented. At minimum, test these end-to-end workflows:

1. Register a customer.
2. Register a vehicle for that customer.
3. Create a job card with a unique organisation-scoped number.
4. Assign a mechanic.
5. Complete and submit an inspection.
6. Create a quotation with correct line totals and tax configuration.
7. Send and record approval for the exact quotation version.
8. Reserve and issue stock with correct stock ledger entries.
9. Complete repair and quality inspection.
10. Issue an invoice that cannot be silently edited.
11. Record a payment and verify allocated amount and outstanding balance.
12. Verify customer portal access is limited to that customer's records.
13. Record notification status and handle provider failure.
14. Restore a backup into a test environment successfully.

Also test:
- Cross-organisation record access attempts.
- Users attempting actions outside their permissions.
- Duplicate payment submissions.
- Concurrent stock reservations/issues.
- Invalid job status transitions.
- Approval links that are expired, revoked, or already used.
- Uploads with invalid type or excessive size.
- Accidental deletion and archival behaviour.
- Partial goods deliveries and returns.
- Failed background jobs and retry behaviour.

Never mark a phase complete because the UI looks finished. Verify the API, database effects, authorization, error states, and tests.

---

## 14. Coding standards and working method

### Before changing code
1. Read this file.
2. Inspect the existing repository structure and relevant files.
3. Identify the affected domain and existing conventions.
4. Check whether migrations, tests, or documentation already exist.
5. State a short implementation plan for non-trivial work.

### While implementing
- Make small, coherent changes.
- Keep functions and components focused.
- Use explicit types; avoid `any` unless justified.
- Validate input at API boundaries.
- Keep business rules in backend services/domain logic.
- Keep route handlers thin.
- Use database transactions for multi-record operations.
- Add indexes and constraints when introducing query patterns or invariants.
- Add tests alongside implementation.
- Keep secrets out of logs and source.
- Reuse established components without forcing unrelated screens into one abstraction.
- Do not add dependencies without a reason.
- Do not replace working architecture or rewrite large areas without first explaining why.

### Frontend standards
- Use TypeScript strict mode.
- Use reusable, accessible form and table components.
- Validate forms with Zod and handle API errors clearly.
- Keep server/client component boundaries deliberate.
- Avoid putting business calculations only in the browser.
- Include loading, empty, error, and success states.
- Do not hardcode example data into production screens. Use clearly marked seed/demo data only in development.

### Backend standards
- Use Pydantic request/response schemas.
- Use SQLAlchemy 2.x patterns consistently.
- Use Alembic for every schema change.
- Apply tenant and permission checks to every protected operation.
- Use transactions and idempotency where duplicate operations are dangerous.
- Return stable, documented API errors.
- Keep external integrations behind service/adaptor boundaries.

### Completion report
At the end of a task, report:
- What changed.
- Important files created or modified.
- Database migrations added.
- Tests run and their results.
- Commands needed to run or verify the feature.
- Known limitations or follow-up work.

Do not claim tests passed unless they were actually run. If a test could not be run, state why.

---

## 15. Local development commands

Adapt commands to the repository's actual scripts and service names. Keep the README accurate.

Typical Docker Compose workflow:

```bash
# Start services
docker compose up -d --build

# Inspect service status
docker compose ps

# Follow logs
docker compose logs -f

# Stop services
docker compose down

# Stop and remove local volumes only when intentionally resetting local data
docker compose down -v
```

Never run `docker compose down -v` unless the user explicitly intends to delete local database volumes or you have clearly warned them and received confirmation.

Typical frontend commands (if defined in package scripts):

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run build
```

Typical backend commands (adapt to the chosen environment manager):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```

Run migrations using the project's configured Alembic command, commonly:

```bash
alembic upgrade head
```

Do not assume these commands work until the actual project configuration has been inspected.

---

## 16. Important product decisions and non-goals

These decisions are deliberate. Do not silently change them:

- Product name: **WorkshopPro**.
- Market: Namibia first; design so other markets can be supported later.
- Default currency: **NAD**.
- Commercial model: once-off installation plus maintenance agreement.
- Application: responsive web app for mobile, tablet, and desktop.
- Core architecture: modular monolith.
- Database: PostgreSQL.
- Backend: FastAPI.
- Frontend: Next.js + TypeScript.
- Deployment starting point: Docker Compose.
- Include inventory, WhatsApp notifications, invoicing/payment records, customer portal, supplier management, and vehicle inspection checklist in the overall product scope.
- Build in phases; do not attempt all modules in the first milestone.
- No full offline mode in the first release.
- No card payment processing in the initial release; record payment methods and transactions.
- No full accounting/general ledger in the initial release.
- No Kubernetes or microservices without a demonstrated need.
- Do not assume tax rules; make configuration possible and verify with a qualified local adviser.
- Do not use unofficial WhatsApp Web automation.
- Do not start chargeable repairs without recorded customer approval or a documented authorised exception.

---

## 17. First task for Claude Code

When beginning work in a new repository:

1. Inspect the repository and report what already exists.
2. Compare the current implementation with this specification.
3. Identify missing setup, risky assumptions, and existing work that should be preserved.
4. Propose a short Phase 0 implementation plan.
5. Do not start implementing every module.
6. Once the plan is clear, implement Phase 0 only, verify it, and provide a completion report.

The first meaningful business workflow after the foundation should be:

**Customer → Vehicle → Inspection → Job Card → Mechanic Assignment**

Build that workflow end-to-end before expanding into the full feature set.
