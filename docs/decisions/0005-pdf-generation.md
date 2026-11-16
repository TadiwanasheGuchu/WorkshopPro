# ADR 0005 — PDFs generated on request with ReportLab

- Status: accepted
- Date: 2026-11-16

## Context
Phase 3 needs customer-facing PDFs: quotations, invoices, credit notes, receipts and inspection reports. The original plan put PDF generation on Celery. Options considered:

- **HTML → PDF (WeasyPrint, headless Chromium):** reuses web styling, but adds large system dependencies (Pango/Cairo or a browser) to the backend image and is slow per document.
- **ReportLab:** pure Python with a small C extension, no system packages or fonts needed, renders a typical document in well under 100 ms.
- **Background generation (Celery) with stored files:** needed only if documents are slow or must be archived as files.

## Decision
- Use ReportLab (`app/documents/`) and generate PDFs synchronously in the request (`GET /…/pdf`). Nothing is stored; each PDF reflects the record as it is now.
- Build each PDF from the same read model the JSON API returns, loaded through the same permission-checked service. A PDF is never more visible than the record, and no amounts are recalculated in the document code.
- Use the built-in Helvetica font. IBM Plex (the UI font) would need TTF files in the image; it can be embedded later without changing the layout code.
- Escape all user-entered text before it reaches ReportLab's paragraph markup.
- Defer Celery to Phase 5, where email/WhatsApp delivery and retries genuinely need it.

## Consequences
- No new infrastructure. Responses carry `Cache-Control: private, no-store`.
- Issued invoices and credit notes are immutable in the database, so regenerating them always produces the same lines and totals. Balances and payment lists on an invoice PDF are as of the moment it is downloaded.
- If archived copies are needed later (for example, PDFs attached to sent emails in Phase 5), the same functions can write the bytes to object storage from a worker.
- The document title is "Invoice". Whether VAT-registered workshops must title it "Tax invoice", and what else Namibian VAT rules require on the document, must be confirmed with a local tax adviser (CLAUDE.md §3.9) before adding it as a setting.
