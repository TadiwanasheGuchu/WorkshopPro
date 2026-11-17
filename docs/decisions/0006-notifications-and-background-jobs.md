# ADR 0006 — Customer notifications through a Celery worker and a provider interface

- Status: accepted
- Date: 2026-11-17

## Context
Phase 5 sends customers WhatsApp and email messages (vehicle received, quotation ready, ready for collection, invoice issued). CLAUDE.md §3.10 requires: the official WhatsApp Business Platform or an approved provider (never WhatsApp Web automation), stored consent, provider references and failure reasons, retries through background jobs, no credentials in the browser, and a workflow that keeps working when a provider is down.

## Decision
- **Celery with the existing Redis as broker.** One `worker` service in Compose (backend image) runs delivery and, with `--beat`, a five-minute sweep that re-queues notifications stuck in `queued` (for example after a Redis outage). Results are not stored.
- **Notification log in PostgreSQL.** The workshop event writes a `notifications` row in its own transaction (channel chosen, text rendered) and enqueues delivery only after the commit. The row is the source of truth for status: queued, sent, delivered, read, failed, skipped (with the reason).
- **Retries.** Adaptors raise `TransientDeliveryError` (network, timeouts, 429, 5xx) or `PermanentDeliveryError` (refused recipient, 4xx). Transient failures are retried with exponential backoff up to six attempts, then marked failed. Staff can retry failed messages.
- **Single-use links are never stored.** Quotation approval links travel only in the task message; the log shows `[customer link]`. A failed link message cannot be retried; staff create a new link instead.
- **Provider interface.** `WhatsAppSender` with two implementations: `log` (default; records without sending) and `meta` (WhatsApp Cloud API, approved templates, credentials from the environment). Delivery receipts arrive at `POST /api/v1/webhooks/whatsapp`, verified with the app secret (HMAC-SHA256); the endpoint is disabled until the secret is set. Another approved provider (a local BSP) is one more adaptor.
- **Channel rules.** WhatsApp requires current WhatsApp consent, a phone number convertible to international format, and an approved template name for the event. Service emails go out unless email consent was withdrawn. The customer's preferred contact method decides the order.
- **Templates.** Per-event email wording and WhatsApp template names are editable (`notifications.manage`). Placeholders are restricted to a fixed list per event; attribute access and format specs are rejected.

## Consequences
- The job workflow never waits on a provider; tests prove a provider outage does not block job creation and that the sweep delivers later.
- Security emails (invitations, password resets) still use the in-request background task; they can move to the worker later.
- Running more than one worker with `--beat` would duplicate the sweep (harmless, but wasteful); run beat exactly once.
- WhatsApp templates must be created and approved in Meta Business Manager before the `meta` provider is switched on; their body parameters must match the order shown on the template screen.
