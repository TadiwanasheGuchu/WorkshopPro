"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Line, LineItemsEditor, linesInvalid, linesPayload, toLine } from "@/components/app/line-items-editor";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { Invoice, Payment, PaymentMethod, TaxRate } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { PAYMENT_METHOD, newIdempotencyKey } from "@/lib/invoice";

const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

export function InvoiceDraftEditor({ invoice, taxRates }: { invoice: Invoice; taxRates: TaxRate[] }) {
  const router = useRouter();
  const [lines, setLines] = useState<Line[]>(invoice.items.map(toLine));
  const [dueDate, setDueDate] = useState(invoice.due_date ?? "");
  const [notes, setNotes] = useState(invoice.notes ?? "");
  const [terms, setTerms] = useState(invoice.terms ?? "");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invalid = linesInvalid(lines);
  const touch = () => setDirty(true);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("PUT", `/invoices/${invoice.id}/draft`, {
        due_date: dueDate || null,
        notes: notes.trim() || null,
        terms: terms.trim() || null,
        items: linesPayload(lines),
      });
      setDirty(false);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <LineItemsEditor lines={lines} onChange={(next) => (setLines(next), touch())} taxRates={taxRates} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Due date" hint="Leave empty to use your payment terms from Settings.">
          {(p) => <Input {...p} type="date" value={dueDate} onChange={(e) => (setDueDate(e.target.value), touch())} />}
        </Field>
      </div>
      <Field label="Notes for the customer">
        {(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => (setNotes(e.target.value), touch())} />}
      </Field>
      <Field label="Terms">
        {(p) => <Textarea {...p} rows={3} value={terms} onChange={(e) => (setTerms(e.target.value), touch())} />}
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={busy} disabled={invalid || !dirty} onClick={() => void save()}>
          Save draft
        </Button>
        {dirty ? <span className="text-sm text-muted">Unsaved changes. Totals update when you save.</span> : null}
        {invalid ? <span className="text-sm text-status-danger">Every line needs a description, quantity above 0 and a price (up to 2 decimals).</span> : null}
      </div>
      {!dirty ? <DraftActions invoice={invoice} /> : null}
    </div>
  );
}

function DraftActions({ invoice }: { invoice: Invoice }) {
  const router = useRouter();
  return (
    <div className="flex flex-wrap gap-2 border-t border-border pt-4">
      {invoice.capabilities.issue && invoice.items.length > 0 ? (
        <ConfirmButton
          trigger={<Button variant="primary">Issue invoice</Button>}
          title="Issue this invoice?"
          description={`Total ${formatMoney(invoice.total, invoice.currency_code)}. Issuing assigns the invoice number. After that it cannot be edited; corrections need a credit note.`}
          confirmLabel="Issue invoice"
          onConfirm={async () => {
            await api("POST", `/invoices/${invoice.id}/issue`).catch((e) => {
              throw new Error(errorMessage(e));
            });
            router.refresh();
          }}
        />
      ) : null}
      {invoice.capabilities.delete ? (
        <ConfirmButton
          trigger={<Button>Delete draft</Button>}
          title="Delete this draft?"
          description="The draft has no number yet, so nothing is lost from your records."
          confirmLabel="Delete draft"
          destructive
          onConfirm={async () => {
            await api("DELETE", `/invoices/${invoice.id}`).catch((e) => {
              throw new Error(errorMessage(e));
            });
            router.push(invoice.job_card ? `/job-cards/${invoice.job_card.id}` : "/invoices");
            router.refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run, setError };
}

function MethodSelect({ value, onChange }: { value: PaymentMethod; onChange: (m: PaymentMethod) => void }) {
  return (
    <Field label="Method" required>
      {(p) => (
        <Select {...p} value={value} onChange={(e) => onChange(e.target.value as PaymentMethod)}>
          {Object.entries(PAYMENT_METHOD).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}

/** Record money received against this invoice. Any excess stays as customer credit. */
export function RecordPaymentButton({ invoice }: { invoice: Invoice }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  // One key per intended payment: retries after a network error reuse it, so the
  // payment cannot be recorded twice.
  const [key, setKey] = useState(newIdempotencyKey);
  const [amount, setAmount] = useState(invoice.balance_due);
  const [method, setMethod] = useState<PaymentMethod>("eft");
  const [reference, setReference] = useState("");
  const [receivedOn, setReceivedOn] = useState("");
  const { busy, error, run } = useSubmit();
  const valid = MONEY_RE.test(amount) && Number(amount) > 0;
  const excess = valid ? Number(amount) - Number(invoice.balance_due) : 0;

  return (
    <>
      <Button
        variant="primary"
        onClick={() => {
          // Start from the current balance each time; the page refreshes after a payment.
          setAmount(invoice.balance_due);
          setReference("");
          setReceivedOn("");
          setOpen(true);
        }}
      >
        Record payment
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Record payment for ${invoice.invoice_number}`} description={`Balance due ${formatMoney(invoice.balance_due, invoice.currency_code)}.`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const allocate = Math.min(Number(amount), Number(invoice.balance_due)).toFixed(2);
              await api<Payment>(
                "POST",
                "/payments",
                {
                  branch_id: invoice.branch.id,
                  customer_id: invoice.customer.id,
                  method,
                  amount,
                  reference: reference.trim() || null,
                  received_at: receivedOn ? new Date(`${receivedOn}T12:00:00`).toISOString() : null,
                  allocations: [{ invoice_id: invoice.id, amount: allocate }],
                },
                { idempotencyKey: key },
              );
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Amount received" required error={amount && !valid ? "Enter an amount above 0 with up to 2 decimals." : undefined}>
              {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value.trim())} />}
            </Field>
            <MethodSelect value={method} onChange={setMethod} />
            <Field label="Reference" hint="Bank reference, slip or cheque number.">
              {(p) => <Input {...p} maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} />}
            </Field>
            <Field label="Date received" hint="Leave empty for now.">
              {(p) => <Input {...p} type="date" value={receivedOn} onChange={(e) => setReceivedOn(e.target.value)} />}
            </Field>
          </div>
          {excess > 0 ? <Alert tone="info">{formatMoney(excess.toFixed(2), invoice.currency_code)} is more than the balance and will be kept as customer credit.</Alert> : null}
          {method === "card" ? <p className="text-xs text-muted">Card payments are recorded only; no card is charged.</p> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Record payment
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function CreditNoteButton({ invoice }: { invoice: Invoice }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(Number(invoice.amount_credited) === 0);
  const [reason, setReason] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const { busy, error, run } = useSubmit();
  const remaining = (Number(invoice.total) - Number(invoice.amount_credited)).toFixed(2);
  const canFull = Number(invoice.amount_credited) === 0;
  const valid = reason.trim().length >= 3 && (full || (description.trim() && MONEY_RE.test(amount) && Number(amount) > 0));

  return (
    <>
      <Button onClick={() => setOpen(true)}>Credit note</Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Credit note for ${invoice.invoice_number}`} description={`Up to ${formatMoney(remaining, invoice.currency_code)} can be credited. The invoice itself does not change.`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api("POST", `/invoices/${invoice.id}/credit-notes`, {
                reason: reason.trim(),
                full,
                lines: full ? [] : [{ description: description.trim(), quantity: "1", unit_price: amount }],
              });
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          {canFull ? <Checkbox label="Credit the whole invoice" description="Copies every line onto the credit note." checked={full} onChange={(e) => setFull(e.target.checked)} /> : null}
          {!full ? (
            <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
              <Field label="What is credited" required>
                {(p) => <Input {...p} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />}
              </Field>
              <Field label="Amount" required>
                {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value.trim())} />}
              </Field>
              <p className="text-xs text-muted sm:col-span-2">Credited without tax. To reverse taxed lines, credit the whole invoice and issue a corrected one.</p>
            </div>
          ) : null}
          <Field label="Reason" required hint="Shown on the credit note and kept in the audit log.">
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Issue credit note
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function RefundButton({ invoice }: { invoice: Invoice }) {
  const router = useRouter();
  const overpaid = (-Number(invoice.balance_due)).toFixed(2);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [amount, setAmount] = useState(overpaid);
  const [method, setMethod] = useState<PaymentMethod>("eft");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSubmit();
  const valid = MONEY_RE.test(amount) && Number(amount) > 0 && reason.trim().length >= 3;

  return (
    <>
      <Button onClick={() => (setAmount(overpaid), setOpen(true))}>Refund overpayment</Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title="Refund overpayment" description={`${formatMoney(overpaid, invoice.currency_code)} was overpaid on ${invoice.invoice_number}.`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api("POST", "/refunds", { invoice_id: invoice.id, method, amount, reference: reference.trim() || null, reason: reason.trim() }, { idempotencyKey: key });
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Amount paid back" required>
              {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value.trim())} />}
            </Field>
            <MethodSelect value={method} onChange={setMethod} />
            <Field label="Reference">{(p) => <Input {...p} maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
          </div>
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Record refund
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function StartInvoiceButton({ jobId, label = "Start invoice" }: { jobId: string; label?: string }) {
  const router = useRouter();
  const { busy, error, run } = useSubmit();
  return (
    <div className="flex items-center gap-2">
      {error ? <span className="text-xs text-status-danger">{error}</span> : null}
      <Button
        size="sm"
        variant="primary"
        loading={busy}
        onClick={() =>
          void run(async () => {
            const inv = await api<Invoice>("POST", `/job-cards/${jobId}/invoices`);
            router.push(`/invoices/${inv.id}`);
          })
        }
      >
        {label}
      </Button>
    </div>
  );
}
