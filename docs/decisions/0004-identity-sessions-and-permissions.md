# ADR 0004 — Identity, sessions and permissions

- Status: accepted
- Date: 2026-11-15

## Context
Phase 1 needs sign-in, staff management and enforceable permissions for a product that runs as a dedicated installation per workshop, and may later be hosted for several organisations.

## Decisions

**Server-side sessions, not JWTs.** Signing in creates a `user_sessions` row; the browser receives a random 256-bit token in an HTTP-only, SameSite=Lax cookie (`wp_session`), and only its SHA-256 hash is stored. Sessions expire after 12 hours idle or 7 days absolute (configurable). They can be revoked immediately: sign-out, password change and reset, and deactivation all revoke sessions. JWTs were rejected because they cannot be revoked without the same server-side lookup.

**CSRF: double-submit plus session binding.** Every POST/PUT/PATCH/DELETE must send an `X-CSRF-Token` header equal to the `wp_csrf` cookie (checked in middleware), and for signed-in requests equal to the token stored on the session (checked in the auth dependency).

**Single origin.** The browser only talks to one origin. Nginx routes `/api/*` to FastAPI and everything else to Next.js; in `next dev`, `proxy.ts` does the same. There is no CORS dependency and cookies stay first-party.

**Globally unique emails.** Users sign in with email and password only, with no organisation picker. The consequence: one person working for two organisations needs two email addresses, and the invite endpoint reveals that an email is already registered. This is acceptable for dedicated installations; revisit if a shared multi-tenant hosting model is adopted.

**No public sign-up.** Organisations and their first owner are created with `python -m app.cli create-organisation` during installation. Everyone else is invited by email, using single-use tokens that expire after 7 days. Reset tokens expire after 60 minutes. Links carry the token in the URL fragment so it never reaches server logs.

**Permissions as code, roles as data.** Permission codes live in `app/permissions/catalogue.py`, each with a scope:
- **organisation**: the permission is only satisfied by an organisation-wide role.
- **branch**: the permission may be granted for specific branches.

Organisations create and edit roles (sets of permission codes). A user can hold several roles, each organisation-wide or limited to one branch.

**Owner role.** Each organisation has exactly one owner role. It implicitly holds every permission, including ones added later, and cannot be edited, archived or limited to a branch. An organisation must always keep at least one active owner.

**Escalation rules.** These are enforced in services and covered by tests:
- Users can only grant permissions, or assign and remove roles, whose permissions they hold organisation-wide.
- Only owners can grant or remove the owner role, or change an owner's account.
- Users cannot deactivate themselves.

**Trust boundary for client IPs.** Nginx overwrites `X-Forwarded-For` with the real peer address. The backend trusts that header only because it is reachable solely through Nginx; uvicorn runs with `FORWARDED_ALLOW_IPS=*` inside the Compose network. Next.js passes a client-supplied `X-Forwarded-For` through unchanged, so Next.js must never be the edge in production.

**Rate limits fail open.** Limits are stored in Redis. If Redis is down, sign-in keeps working and a warning is logged.

## Consequences
- Every request does one indexed session lookup plus one permission query. That is negligible at workshop scale.
- New permissions must be added to the catalogue, enforced in a service, and granted to the default role templates with a data migration.
- Email delivery runs as a FastAPI background task until Celery arrives (Phase 3/5), so a failed send is logged but not retried. An admin can resend an invitation.
