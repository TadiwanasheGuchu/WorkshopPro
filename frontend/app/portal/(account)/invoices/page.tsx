import type { Metadata } from "next";

import { PdfLink } from "@/components/app/pdf-link";
import { StatusBadge } from "@/components/status-badge";
import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { DateFormat, PortalInvoice, PortalMe } from "@/lib/api/types";
import { formatDate, formatMoney } from "@/lib/format";
import { invoiceStatus } from "@/lib/invoice";

export const metadata: Metadata = { title: "Invoices" };

export default async function PortalInvoicesPage() {
  const [invoices, me] = await Promise.all([portalGet<PortalInvoice[]>("/invoices"), portalGet<PortalMe>("/me")]);
  const prefs = { timezone: me.timezone, date_format: me.date_format as DateFormat };
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Invoices and receipts</h1>
      <Panel flush>
        {invoices.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">No invoices yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {invoices.map((inv) => {
              const st = invoiceStatus(inv);
              return (
                <li key={inv.id} className="space-y-2 px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>
                      <span className="font-mono">{inv.invoice_number}</span>
                      <span className="block text-xs text-muted">
                        {formatDate(inv.issue_date, prefs)}
                        {inv.job_number ? ` · job ${inv.job_number}` : ""}
                        {inv.due_date ? ` · due ${formatDate(inv.due_date, prefs)}` : ""}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-right font-mono tabular-nums">
                        {formatMoney(inv.total, inv.currency_code)}
                        {Number(inv.balance_due) > 0 ? <span className="block text-xs text-muted">owed {formatMoney(inv.balance_due, inv.currency_code)}</span> : null}
                      </span>
                      <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                      <PdfLink href={`/portal/invoices/${inv.id}/pdf`} />
                    </span>
                  </div>
                  {inv.receipts.length ? (
                    <ul className="space-y-1 border-l-2 border-border pl-3">
                      {inv.receipts.map((r) => (
                        <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
                          <span>
                            Receipt <span className="font-mono">{r.number}</span> · {formatDate(r.date, prefs)}
                          </span>
                          <PdfLink href={`/portal/receipts/${r.id}/pdf`} label="Receipt" />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
