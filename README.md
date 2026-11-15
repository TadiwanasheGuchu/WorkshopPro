# WorkshopPro

Automotive workshop management for garages and service centres in Namibia: customers, vehicles, inspections, job cards, quotations, inventory, invoicing and payments.

Project rules and product specification: [`CLAUDE.md`](CLAUDE.md). Phase plan and progress: [`docs/development-plan.md`](docs/development-plan.md).

**Current state:** Phase 0 (technical foundation) complete. No business features yet.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript strict, Tailwind CSS 4, Zod |
| Backend | Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Runtime | Docker Compose |

## Quick start (Docker)

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app (currently a system status page) |
| http://localhost:8000/api/v1/health/live | API liveness |
| http://localhost:8000/api/v1/health/ready | API readiness (PostgreSQL + Redis) |
| http://localhost:8000/api/docs | OpenAPI docs (disabled when `ENVIRONMENT=production`) |

The backend applies database migrations automatically on start (`RUN_MIGRATIONS=false` disables this).

All ports bind to `127.0.0.1` only. Change them in `.env` if they clash with local services.

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
uv run uvicorn app.main:app --reload
```

Checks:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

Tests marked `db` run against `DATABASE_URL`/`REDIS_URL` and skip automatically if those are unreachable.

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

Checks:

```bash
npm run lint && npm run typecheck && npm run build
```

## Repository layout

```text
backend/            FastAPI app (app/), Alembic migrations, tests
frontend/           Next.js app
docs/               Architecture, database conventions, decisions, plan
infrastructure/     Reverse proxy, backup and monitoring config (from Phase 6)
docker-compose.yml  Local and single-server deployment
```
