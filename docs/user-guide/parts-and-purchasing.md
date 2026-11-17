# Parts and purchasing

Stock is tracked as a ledger: every change (delivery, issue to a job, return, adjustment,
transfer) is a movement with who, when and why. On-hand quantities are calculated from
those movements and cannot be typed over. Stock cannot go below zero, or below what is
reserved for jobs.

## Parts catalogue

**Parts → Add part**: SKU, name, category, manufacturer part number, cost and selling
price, tax treatment, and a **minimum quantity** per location for low-stock warnings.
Search by SKU, name or manufacturer number.

## Stock on hand

Open a part to see stock per location: on hand, reserved for jobs, and available.

- **Record adjustment** for stocktakes, damage or losses. A reason is required and the
  adjustment appears in the audit log.
- **Transfer** moves stock between locations or branches.
- **Stock movements** lists the full ledger with filters.

## Parts on jobs

On the job card's **Parts** panel:

1. **Reserve** parts once the quotation is approved. Reserved stock cannot be used by
   another job.
2. **Issue parts** when they are actually handed to the mechanic. Issuing removes them
   from stock. Quoted parts are not taken from stock until issued.
3. **Return** unused parts to stock; **Release** a reservation that is no longer needed.

Reservations are released automatically when a job is completed or cancelled.

## Suppliers

**Suppliers → Add supplier** with contact details, tax number, your account number with
them, payment terms and lead time. Under **Part codes and prices**, record the supplier's
own code and price for each part. The supplier page lists recent purchase orders and
what was received in the last 90 days. Supplier invoices are paid in the workshop's
accounting system; WorkshopPro records the supplier invoice reference on each delivery.

## Purchase orders

1. **Purchase orders → Choose a supplier**, add lines (part, quantity, expected cost) and
   the expected delivery date. Save as a draft.
2. **Approve order** (needs purchasing approval permission). Send the PDF to the supplier.
3. When goods arrive, **Record delivery**: enter what actually arrived. Partial deliveries
   are normal; the order stays open until everything is received or it is closed. Record
   the supplier's invoice reference. Received stock goes into the location you choose and
   the part's cost is updated to the latest delivery cost.
4. Faulty or wrong goods: **Record return** against the order.

## Low stock and stock checks

**Reports → Inventory** shows parts at or below minimum, stock value at cost by category,
parts issued to jobs, deliveries and returns in a period, and a **Stock check** that
confirms on-hand and reserved figures still match the ledger. If it reports differences,
contact support.
