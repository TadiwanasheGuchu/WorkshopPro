"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { InvoiceListItem, Payment } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { newIdempotencyKey } from "@/lib/invoice";

const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

export function ReversePaymentButton({ payment }: { payment: Payment }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <Button onClick={() => setOpen(true)}>Reverse payment</Button>
      <Dialog
        open={open}
        onOpenChange={(o) => !busy && setOpen(o)}
        title={`Reverse ${payment.receipt_number}?`}
        description="Use this for payments recorded in error, such as a bounced EFT or the wrong customer. Every allocation is undone and invoice balances go back up. This cannot be undone."
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              const r = await api<Payment>("POST", `/payments/${payment.id}/reverse`, { reason: reason.trim() }, { idempotencyKey: key });
              setKey(newIdempotencyKey());
              setOpen(false);
              router.push(`/payments/${r.id}`);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={busy} disabled={reason.trim().length < 3}>
              Reverse payment
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

/** Apply credit left on a payment (a deposit or overpayment) to one of the customer's open invoices. */
export function AllocateCreditButton({ payment, openInvoices }: { payment: Payment; openInvoices: InvoiceListItem[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [invoiceId, setInvoiceId] = useState(openInvoices[0]?.id ?? "");
  const selected = openInvoices.find((i) => i.id === invoiceId);
  const suggested = (inv?: InvoiceListItem) => (inv ? Math.min(Number(payment.unallocated), Number(inv.balance_due)).toFixed(2) : "");
  const [amount, setAmount] = useState(suggested(openInvoices[0]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = Boolean(selected) && MONEY_RE.test(amount) && Number(amount) > 0;

  if (!openInvoices.length) return <p className="text-sm text-muted">The customer has no open invoices to apply this credit to.</p>;

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Apply credit to an invoice
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title="Apply credit" description={`${formatMoney(payment.unallocated, payment.currency_code)} is available on ${payment.receipt_number}.`}>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("POST", `/payments/${payment.id}/allocations`, { allocations: [{ invoice_id: invoiceId, amount }] });
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Invoice" required>
            {(p) => (
              <Select
                {...p}
                value={invoiceId}
                onChange={(e) => {
                  setInvoiceId(e.target.value);
                  setAmount(suggested(openInvoices.find((i) => i.id === e.target.value)));
                }}
              >
                {openInvoices.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.invoice_number} · due {formatMoney(i.balance_due, i.currency_code)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Amount" required>
            {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value.trim())} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Apply credit
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
