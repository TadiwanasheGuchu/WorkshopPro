# WorkshopPro

Automotive workshop management for garages and service centres in Namibia: customers, vehicles, inspections, job cards, quotations, inventory, invoicing and payments.

Project rules and product specification: [`CLAUDE.md`](CLAUDE.md). Phase plan and progress: [`docs/development-plan.md`](docs/development-plan.md).

**Current state:** Phases 0–5 complete. Staff app: sign-in and permissions; organisation, branches and settings; customers and vehicles; job cards with an enforced workflow and approval rule; mechanic assignment; mobile inspections with photos; appointments and booking requests; quotations with versioned customer approval; immutable invoices, credit notes and idempotent payments; PDF documents; parts catalogue, stock ledger, reservations and parts issued to jobs; suppliers, purchase orders and goods received; financial, operations and inventory reports; WhatsApp/email notifications with consent, retries and service reminders. Customer portal: sign-in by emailed link, job progress, quotation approval, invoices and receipts, booking requests, contact preferences. Production readiness and a pilot (Phase 6) are next.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript strict, Tailwind CSS 4, Radix UI, React Hook Form, Zod |
| Backend | Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Runtime | Docker Compose, nginx edge, Celery worker (notifications, retries), SeaweedFS (S3-compatible photo storage), Mailpit (local email) |

## Quick start (Docker)

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps
```

Create the organisation and its owner account. There is no public sign-up; you are prompted for the owner's password:

```bash
docker compose exec backend python -m app.cli create-organisation \
  --name "Your Workshop" --owner-email you@example.com --owner-name "Your Name"
```

Then sign in at http://localhost:3000 and invite staff from **Users & roles**.

| URL | What |
|---|---|
| http://localhost:3000 | Web app (nginx routes `/api` to the backend) |
| http://localhost:3000/api/v1/health/ready | API readiness (PostgreSQL + Redis) |
| http://localhost:3000/api/docs | OpenAPI docs (disabled when `ENVIRONMENT=production`) |
| http://localhost:8025 | Mailpit: all emails sent locally (invitations, password resets, customer notifications) |

The backend applies database migrations automatically on start (`RUN_MIGRATIONS=false` disables this).

Photos are stored in the bundled SeaweedFS (S3-compatible, not published); set `STORAGE_*` to use a managed S3-compatible service instead. Only nginx (and Mailpit) are published, on `127.0.0.1`. Set `WEB_BIND=0.0.0.0` to serve the local network on an on-premises install. For production, set `ENVIRONMENT=production`, a real `SMTP_*` server, `APP_BASE_URL`, and serve over HTTPS.

```bash
docker compose logs -f backend      # follow API logs
docker compose down                 # stop, keep data
```

`docker compose down -v` **deletes the database volume**. Only use it when you intend to wipe local data.

## Local development without Docker

### Backend

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/), plus PostgreSQL and Redis (run just those two with `docker compose up -d postgres redis`).

```bash
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://workshoppro:<password>@localhost:5432/workshoppro
uv run alembic upgrade head
uv run python -m app.cli create-organisation --name "Dev Workshop" --owner-email dev@example.com --owner-name Dev
uv run uvicorn app.main:app --reload
```

Checks:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Tests use a separate database (`<DATABASE_URL name>_test`, created and migrated automatically) and Redis database 15; they skip if PostgreSQL or Redis is unreachable. The role in `DATABASE_URL` needs `CREATEDB`, or set `TEST_DATABASE_URL`.

New migration:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

### Frontend

Requires Node.js 22.

```bash
cd frontend
npm install
API_INTERNAL_URL=http://localhost:8000 npm run dev
```

In development `proxy.ts` forwards `/api/*` to `API_INTERNAL_URL`, so the browser uses a single origin just like behind nginx.

Checks:

```bash
npm run lint && npm run typecheck && npm run build
```

End-to-end tests (Playwright) run against the Compose stack. See [`frontend/tests/e2e/README.md`](frontend/tests/e2e/README.md).

## Repository layout

```text
backend/            FastAPI app (app/), Alembic migrations, tests
frontend/           Next.js app
docs/               Architecture, database conventions, decisions, plan
infrastructure/     nginx edge config; backup and monitoring config (Phase 6)
docker-compose.yml  Local and single-server deployment
```
