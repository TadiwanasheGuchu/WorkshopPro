import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PdfLink } from "@/components/app/pdf-link";
import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { CustomerBalance, Payment } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { PAYMENT_KIND, PAYMENT_METHOD } from "@/lib/invoice";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { AllocateCreditButton, ReversePaymentButton } from "./payment-actions";

export const metadata: Metadata = { title: "Payment" };

export default function PaymentPage({ params }: PageProps<"/payments/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/payments/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVOICES_VIEW)) return <NoAccess />;
  const { id } = await params;
  const p = await apiGet<Payment>(`/payments/${id}`);
  const prefs = me.organisation;
  const c = p.currency_code;
  const isPayment = p.kind === "payment";
  const reversed = Boolean(p.reversed_by_receipt);
  const canAllocate = isPayment && !reversed && Number(p.unallocated) > 0 && can(me, P.PAYMENTS_RECORD, p.branch.id);
  const balance = canAllocate ? await apiGet<CustomerBalance>(`/customers/${p.customer.id}/balance`) : null;
  const canReverse = isPayment && !reversed && can(me, P.PAYMENTS_REFUND, p.branch.id);

  return (
    <>
      <PageHeader
        title={`${PAYMENT_KIND[p.kind]} ${p.receipt_number}`}
        description={p.customer.name}
        back={{ href: "/payments", label: "Payments" }}
        actions={
          <span className="flex items-center gap-2">
            {reversed ? <StatusBadge tone="danger">Reversed</StatusBadge> : null}
            <PdfLink href={`/payments/${p.id}/pdf`} />
          </span>
        }
      />
      {reversed ? (
        <Alert tone="error" className="mb-4">
          Reversed by {p.reversed_by_receipt}. It no longer counts towards any invoice.
        </Alert>
      ) : null}
      {p.reverses_receipt ? (
        <Alert tone="info" className="mb-4">
          Reverses payment {p.reverses_receipt}. Reason: {p.notes}
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-5">
          <Panel title="Receipt">
            <DetailList
              items={[
                { label: "Amount", value: <span className="font-mono tabular-nums">{formatMoney(p.amount, c)}</span> },
                { label: "Method", value: PAYMENT_METHOD[p.method] },
                { label: isPayment ? "Received" : "Paid out", value: formatDateTime(p.received_at, prefs) },
                { label: "Reference", value: p.reference },
                { label: "Branch", value: p.branch.name },
                { label: "Recorded by", value: p.recorded_by },
                ...(p.notes && !p.reverses_receipt ? [{ label: isPayment ? "Notes" : "Reason", value: p.notes }] : []),
              ]}
            />
          </Panel>
          <Panel title="Applied to invoices" flush>
            {p.allocations.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">Not applied to any invoice.</p>
            ) : (
              <ul className="divide-y divide-border">
                {p.allocations.map((a, i) => (
                  <li key={`${a.invoice_id}-${i}`}>
                    <Link href={`/invoices/${a.invoice_id}`} className="flex justify-between px-4 py-2.5 text-sm hover:bg-mist">
                      <span className="font-mono text-steel">{a.invoice_number}</span>
                      <span className="font-mono tabular-nums">{formatMoney(a.amount, c)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
        <div className="space-y-5">
          {isPayment && !reversed ? (
            <Panel title="Customer credit">
              <p className="font-mono text-lg tabular-nums">{formatMoney(p.unallocated, c)}</p>
              <p className="mb-3 text-xs text-muted">Received but not yet applied to an invoice.</p>
              {canAllocate && balance ? <AllocateCreditButton payment={p} openInvoices={balance.open_invoices} /> : null}
            </Panel>
          ) : null}
          {canReverse ? (
            <Panel title="Correct a mistake">
              <ReversePaymentButton payment={p} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
