import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { Panel } from "@/components/ui/page";
import type { InvoiceListItem, JobCardDetail } from "@/lib/api/types";
import { type Prefs, formatDate, formatMoney } from "@/lib/format";
import { invoiceStatus } from "@/lib/invoice";

import { StartInvoiceButton } from "../../invoices/[id]/invoice-actions";

// Work is invoiced once it has passed (or reached) quality inspection.
const INVOICEABLE = ["quality_inspection", "ready_for_collection", "completed"];

export function InvoicesPanel({ job, invoices, canManage, prefs }: { job: JobCardDetail; invoices: InvoiceListItem[]; canManage: boolean; prefs: Prefs }) {
  const hasDraft = invoices.some((i) => i.status === "draft");
  const canStart = canManage && !hasDraft && INVOICEABLE.includes(job.status);
  return (
    <Panel title="Invoices" flush actions={canStart ? <StartInvoiceButton jobId={job.id} label={invoices.length ? "New invoice" : "Start invoice"} /> : null}>
      {invoices.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted">{INVOICEABLE.includes(job.status) ? "Not invoiced yet." : "The job can be invoiced from quality inspection onwards."}</p>
      ) : (
        <ul className="divide-y divide-border">
          {invoices.map((i) => {
            const st = invoiceStatus(i);
            return (
              <li key={i.id}>
                <Link href={`/invoices/${i.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
                  <div>
                    <p className="font-mono font-medium text-steel">{i.invoice_number ?? "Draft"}</p>
                    <p className="text-xs text-muted">{i.status === "issued" ? `Balance due ${formatMoney(i.balance_due, i.currency_code)} · due ${formatDate(i.due_date, prefs)}` : "Not issued"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono tabular-nums">{formatMoney(i.total, i.currency_code)}</span>
                    <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
