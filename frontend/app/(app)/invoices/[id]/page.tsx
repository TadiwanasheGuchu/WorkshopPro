import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { DocumentLines } from "@/components/app/document-lines";
import { PdfLink } from "@/components/app/pdf-link";
import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Invoice, TaxRate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { PAYMENT_KIND, PAYMENT_METHOD, invoiceStatus } from "@/lib/invoice";
import { P, canInAnyBranch } from "@/lib/permissions";

import { CreditNoteButton, InvoiceDraftEditor, RecordPaymentButton, RefundButton } from "./invoice-actions";

export const metadata: Metadata = { title: "Invoice" };

export default function InvoicePage({ params }: PageProps<"/invoices/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/invoices/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVOICES_VIEW)) return <NoAccess />;
  const { id } = await params;
  const inv = await apiGet<Invoice>(`/invoices/${id}`);
  const editing = inv.capabilities.edit;
  const taxRates = editing ? await apiGet<TaxRate[]>("/organisation/tax-rates") : [];
  const prefs = me.organisation;
  const st = invoiceStatus(inv);
  const c = inv.currency_code;
  const caps = inv.capabilities;

  return (
    <>
      <PageHeader
        title={inv.invoice_number ?? "Draft invoice"}
        description={
          <>
            {inv.customer.name}
            {inv.job_card ? (
              <>
                {" · "}
                <Link href={`/job-cards/${inv.job_card.id}`} className="font-mono text-steel hover:underline">
                  {inv.job_card.name}
                </Link>
              </>
            ) : null}
            {" · "}
            {inv.branch.name}
          </>
        }
        back={{ href: "/invoices", label: "Invoices" }}
        actions={
          <span className="flex items-center gap-2">
            <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
            <PdfLink href={`/invoices/${inv.id}/pdf`} />
          </span>
        }
      />

      {editing && inv.quotation_version_id ? (
        <Alert tone="info" className="mb-4">
          Prefilled from the approved quotation. Adjust lines for work actually done before issuing.
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-5">
          <Panel title={editing ? "Lines" : "Invoice"}>
            {editing ? (
              <>
                {inv.items.length ? (
                  <div className="mb-5 border-b border-border pb-5">
                    <DocumentLines document={inv} />
                  </div>
                ) : null}
                <InvoiceDraftEditor key={inv.total + inv.items.length + (inv.due_date ?? "")} invoice={inv} taxRates={taxRates} />
              </>
            ) : (
              <>
                <DocumentLines document={inv} />
                {inv.notes ? <p className="mt-4 text-sm whitespace-pre-line">{inv.notes}</p> : null}
                {inv.terms ? <div className="mt-4 border-t border-border pt-3 text-xs whitespace-pre-line text-muted">{inv.terms}</div> : null}
              </>
            )}
          </Panel>

          {caps.record_payment || caps.credit || caps.refund ? (
            <section aria-label="Actions" className="flex flex-wrap gap-2 rounded-panel border border-border bg-surface p-4">
              {caps.record_payment ? <RecordPaymentButton invoice={inv} /> : null}
              {caps.refund ? <RefundButton invoice={inv} /> : null}
              {caps.credit ? <CreditNoteButton invoice={inv} /> : null}
            </section>
          ) : null}

          {inv.status === "issued" ? (
            <Panel title="Payments" flush>
              {inv.payments.length === 0 ? (
                <p className="px-4 py-3 text-sm text-muted">No payments recorded.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {inv.payments.map((p, i) => (
                    <li key={`${p.payment_id}-${i}`}>
                      <Link href={`/payments/${p.payment_id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-mist">
                        <span>
                          <span className="font-mono text-steel">{p.receipt_number}</span>
                          <span className="block text-xs text-muted">
                            {PAYMENT_KIND[p.kind]} · {PAYMENT_METHOD[p.method]} · {formatDateTime(p.received_at, prefs)}
                          </span>
                        </span>
                        <span className="font-mono tabular-nums">{formatMoney(p.amount, c)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          ) : null}

          {inv.credit_notes.length ? (
            <Panel title="Credit notes" flush>
              <ul className="divide-y divide-border">
                {inv.credit_notes.map((cn) => (
                  <li key={cn.id} className="flex items-start justify-between gap-3 px-4 py-2.5 text-sm">
                    <span>
                      <span className="font-mono">{cn.credit_note_number}</span>
                      <span className="block text-xs text-muted">
                        {formatDate(cn.issue_date, prefs)} · {cn.created_by} · {cn.reason}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="font-mono tabular-nums">{formatMoney(cn.total, c)}</span>
                      <PdfLink href={`/credit-notes/${cn.id}/pdf`} label={`${cn.credit_note_number} PDF`} />
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </div>

        <div className="space-y-5">
          <Panel title="Balance">
            <dl className="space-y-1.5 text-sm">
              <Row label="Invoice total" value={formatMoney(inv.total, c)} />
              <Row label="Credited" value={formatMoney(inv.amount_credited, c)} />
              <Row label="Paid" value={formatMoney(inv.amount_paid, c)} />
              <div className="flex justify-between border-t border-border pt-1.5 text-base font-semibold">
                <dt>{Number(inv.balance_due) < 0 ? "Overpaid" : "Balance due"}</dt>
                <dd className="font-mono tabular-nums">{formatMoney(Math.abs(Number(inv.balance_due)).toFixed(2), c)}</dd>
              </div>
            </dl>
          </Panel>
          <Panel title="Details">
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-xs text-muted">Issued</dt>
                <dd>{inv.issued_at ? `${formatDate(inv.issue_date, prefs)} · ${inv.issued_by ?? ""}` : "Not issued"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Due</dt>
                <dd>
                  {inv.due_date ? formatDate(inv.due_date, prefs) : "Set on issue from payment terms"}
                  {inv.is_overdue ? <span className="ml-2 text-status-danger">Overdue</span> : null}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Customer</dt>
                <dd>
                  <Link href={`/customers/${inv.customer.id}`} className="text-steel hover:underline">
                    {inv.customer.name}
                  </Link>
                </dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono tabular-nums">{value}</dd>
    </div>
  );
}
