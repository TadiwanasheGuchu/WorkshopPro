# Invoices and payments

WorkshopPro records workshop invoices and payments. It is not a full accounting package:
export or re-enter totals into the workshop's accounting system as agreed with the
accountant. Tax rates are configured by the owner after confirming them with the
workshop's accountant or tax adviser.

## Invoices

On the job card's **Invoices** panel, **Start invoice**. If an approved quotation exists,
its lines are copied in. Add or correct labour, parts, fees and discounts; **Save draft**.
Drafts can be edited or deleted (**Delete draft**).

**Issue invoice** gives it its number and date and locks it. Issued invoices can never be
edited. The customer is notified if they agreed to messages. The PDF is available from the
invoice page and in the customer portal.

To correct an issued invoice, **Issue credit note** for the amount and reason, then issue
a new invoice if needed.

## Payments

**Record payment** on the invoice. Choose the method (cash, EFT, card, mobile, cheque,
other), the amount, date and any reference (for example the EFT
reference). Part payments are fine; the invoice shows **amount paid** and **balance due**.

- If the customer pays more than the balance, the extra stays on their account as
  credit. Open the payment and use **Apply credit** to put it against another invoice,
  or **Refund overpayment** to pay it back.
- Each payment gets a **receipt** number and PDF.
- Pressing save twice, or a slow connection retrying, never records a payment twice.

Mistakes: payments cannot be edited or deleted. Use **Reverse payment** (for example a
bounced EFT) with a reason; the invoice balance goes back up. Then record the correct
payment. Money paid back after a credit note is recorded with **Record refund** on the
invoice.

Card payments are recorded only; WorkshopPro does not process cards.

## Customer balances

The customer page shows what is owed on issued invoices and any unapplied credit.
**Invoices** can be filtered by outstanding, overdue (past due date) and paid.

## Reports

**Reports → Financial** for an explicit period:

- **Net invoiced**: invoices issued minus credit notes in the period (revenue billed).
- **Net received**: payments received minus refunds in the period (cash in).
- Outstanding receivables now, by payment method, by day.

Invoiced is not the same as received; the report keeps them separate. **How these
figures are calculated** explains each figure.
