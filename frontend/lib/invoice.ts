import type { StatusTone } from "@/components/status-badge";

import type { InvoicePaymentStatus, PaymentKind, PaymentMethod } from "./api/types";

export const INVOICE_STATUS: Record<InvoicePaymentStatus, { tone: StatusTone; label: string }> = {
  draft: { tone: "neutral", label: "Draft" },
  unpaid: { tone: "active", label: "Issued" },
  partially_paid: { tone: "waiting", label: "Partially paid" },
  paid: { tone: "success", label: "Paid" },
  credited: { tone: "neutral", label: "Credited" },
  overpaid: { tone: "waiting", label: "Overpaid" },
};

export function invoiceStatus(i: { payment_status: InvoicePaymentStatus; is_overdue: boolean }): { tone: StatusTone; label: string } {
  return i.is_overdue ? { tone: "danger", label: "Overdue" } : INVOICE_STATUS[i.payment_status];
}

export const PAYMENT_METHOD: Record<PaymentMethod, string> = {
  cash: "Cash",
  eft: "EFT / bank transfer",
  card: "Card (recorded only)",
  mobile: "Mobile money",
  cheque: "Cheque",
  other: "Other",
};

export const PAYMENT_KIND: Record<PaymentKind, string> = { payment: "Payment", refund: "Refund", reversal: "Reversal" };

/** A fresh key per intended payment, so a double click or retry cannot record it twice. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
