# ADR 0001 — Modular monolith with Next.js, FastAPI and PostgreSQL

- Status: accepted
- Date: 2026-11-15

## Context
WorkshopPro is sold as a once-off installation, either as a managed dedicated deployment or on the customer's own hardware. Pilot load is a few dozen concurrent staff per installation. Maintenance is done by a small team.

## Decision
- One FastAPI backend and one Next.js frontend, deployed with Docker Compose.
- PostgreSQL is the only system of record. Redis is for rate limiting, cache and queues only.
- Domain boundaries are kept by package structure (`services/`, `repositories/` per domain), not by network boundaries.
- No microservices, Kubernetes or event streaming unless a measured need appears.

## Consequences
- A single deployable unit per customer keeps on-premises installs and upgrades simple.
- Cross-domain operations (issuing stock against a job and updating a quotation) can use one database transaction.
- Domain discipline has to be enforced in review, because nothing at the network level stops cross-module imports.
