# Free hosted demo (Render + Neon + Upstash)

A public demo of WorkshopPro on free tiers, for showing the product. **Not for real
workshops or real customer data**: use the [installation runbook](installation.md) for
that.

| Piece | Free service | Holds |
|---|---|---|
| API (`workshoppro-api`) | Render web service (Docker) | — |
| Web app (`workshoppro-web`) | Render web service (Docker) | — |
| Database | Neon PostgreSQL (0.5 GB) | all data, including photos |
| Redis | Upstash Redis | sign-in rate limits, cache |

## What is different from a real installation

- **Sleeps when idle.** Render free services stop after 15 minutes without visitors; the
  next visit takes about a minute while both wake up. Open the site a few minutes before
  a demo.
- **No background worker.** Customer messages are delivered during the request instead of
  by the worker. The retry sweep and automatic service reminders do not run.
- **Email is not sent.** `EMAIL_PROVIDER=log` records that a message would have been sent
  (visible on the Notifications screen) without sending it. Invitations and password
  reset links therefore do not arrive: use the demo accounts below.
- **Photos are stored in the database** (`STORAGE_BACKEND=database`), because Render free
  services have no disk.
- Runs as `ENVIRONMENT=staging`; the production safety checks would refuse log-only email.

## Set-up (about 20 minutes)

### 1. Neon (database)

1. Sign up at neon.tech and create a project (region: Frankfurt or closest to Namibia,
   PostgreSQL 16).
2. Copy the **connection string** from the dashboard. It looks like
   `postgresql://user:password@ep-....eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   Use the *direct* (not "pooled") connection.

### 2. Upstash (Redis)

1. Sign up at upstash.com and create a Redis database (region: Frankfurt, free plan).
2. Copy the **Redis URL** with TLS: `rediss://default:password@....upstash.io:6379`.

### 3. Render (the two services)

1. Sign up at render.com with GitHub and allow access to the `workshoppro` repository.
2. **New → Blueprint**, choose the repository. Render reads `render.yaml` and proposes
   `workshoppro-api` and `workshoppro-web` on the free plan. The blueprint deploys the
   branch `claude/wizardly-albattani-8fwa52`; change `branch:` in `render.yaml` once the
   work is merged to `main`.
3. Render asks for the values marked "set in the dashboard". The two service addresses
   are `https://workshoppro-api.onrender.com` and `https://workshoppro-web.onrender.com`
   unless Render reports those names are taken (then it shows the actual address on each
   service's page; use those).

   | Service | Variable | Value |
   |---|---|---|
   | api | `DATABASE_URL` | Neon connection string |
   | api | `REDIS_URL` | Upstash `rediss://` URL |
   | api | `APP_BASE_URL` | `https://workshoppro-web.onrender.com` |
   | api | `CORS_ALLOWED_ORIGINS` | same as `APP_BASE_URL` |
   | api | `DEMO_PASSWORD` | a password for the demo accounts (10+ characters) |
   | web | `API_INTERNAL_URL` | `https://workshoppro-api.onrender.com` |

4. **Apply**. The first build takes 5–10 minutes. On first start the API creates the
   database tables and the demo organisation (its log shows the account list).

### 4. Check

Open `https://workshoppro-web.onrender.com`, sign in as
`manager@demo-motors.example.com` with the `DEMO_PASSWORD`, and open a job card.

## Demo accounts

All use `DEMO_PASSWORD`. Each sees only what their role allows.

| Sign in as | Role | Good for showing |
|---|---|---|
| `owner@demo-motors.example.com` | Owner | Settings, users and roles, audit log, reports |
| `manager@demo-motors.example.com` | Workshop manager | Dashboard, assigning, approvals, quality check |
| `reception@demo-motors.example.com` | Service advisor | Customers, receiving a vehicle, quotations, handover |
| `mechanic@demo-motors.example.com` | Mechanic | Phone view: assigned jobs, inspection with photos |
| `parts@demo-motors.example.com` | Inventory manager | Parts, stock, purchase orders, deliveries |
| `accounts@demo-motors.example.com` | Accounts | Invoices, payments, receipts, financial report |

The demo data: six jobs at different stages (just received; overdue in diagnosis;
awaiting quotation approval; repair in progress with parts issued; ready for collection
with a part-paid invoice; collected and paid), six parts with stock, a supplier with a
part-delivered purchase order, and an appointment tomorrow. Every name is marked "(demo)".

A suggested 10-minute walk-through: manager dashboard → overdue job → reception receives a
new vehicle → mechanic (on a phone) does the intake inspection with a photo → reception
prepares and sends a quotation → open the customer link and approve it → parts reserves
and issues → accounts invoices and records a payment → PDF receipt.

## Resetting the demo

Visitors change the data. To start fresh: in Neon, delete and recreate the database (or
run `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` in the SQL editor), then in Render
**Manual deploy → Restart** the API. It recreates everything on start.

## Keeping it safe

- Share the demo address and passwords only with people you are showing it to; change
  `DEMO_PASSWORD` (and reset) after a public showing.
- Do not enter real customer details. Rate limits on sign-in still apply.
- The Neon and Upstash credentials live only in Render's environment settings.
