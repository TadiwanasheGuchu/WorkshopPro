import type { Metadata } from "next";
import Link from "next/link";

import { PdfLink } from "@/components/app/pdf-link";
import { StatusBadge } from "@/components/status-badge";
import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { DateFormat, PortalJobDetail, PortalMe } from "@/lib/api/types";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { JOB_STATUS_TONE } from "@/lib/job-status";

export const metadata: Metadata = { title: "Job progress" };

export default async function PortalJobPage({ params }: PageProps<"/portal/jobs/[id]">) {
  const { id } = await params;
  const [job, me] = await Promise.all([portalGet<PortalJobDetail>(`/jobs/${id}`), portalGet<PortalMe>("/me")]);
  const prefs = { timezone: me.timezone, date_format: me.date_format as DateFormat };

  return (
    <div className="space-y-5">
      <div>
        <Link href="/portal" className="text-sm text-steel hover:underline">
          ← Overview
        </Link>
        <h1 className="mt-1 text-xl font-semibold">{job.vehicle}</h1>
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="font-mono">{job.job_number}</span>
          <StatusBadge tone={JOB_STATUS_TONE[job.status]}>{job.status_label}</StatusBadge>
        </p>
      </div>

      <Panel title="Progress">
        <ol className="space-y-2 text-sm">
          {job.history.map((h, i) => (
            <li key={i} className="flex justify-between gap-3">
              <span>{h.label}</span>
              <span className="text-muted">{formatDateTime(h.at, prefs)}</span>
            </li>
          ))}
        </ol>
        {job.promised_at && !job.collected_at ? <p className="mt-3 text-sm">Expected ready: {formatDateTime(job.promised_at, prefs)}</p> : null}
        <p className="mt-3 text-sm text-muted">Reported: {job.complaint}</p>
        {job.work_performed ? <p className="mt-2 text-sm whitespace-pre-line">Work done: {job.work_performed}</p> : null}
      </Panel>

      {job.quotation ? (
        <Panel title="Quotation" flush>
          <Link href={`/portal/quotations/${job.quotation.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
            <span className="font-mono text-steel">{job.quotation.number}</span>
            <span className="text-sm">{job.quotation.status === "sent" ? "Waiting for your decision" : job.quotation.status}</span>
          </Link>
        </Panel>
      ) : null}

      {job.invoices.length ? (
        <Panel title="Invoices" flush>
          <ul className="divide-y divide-border">
            {job.invoices.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span>
                  <span className="font-mono">{inv.number}</span>
                  <span className="block text-xs text-muted">
                    {formatDate(inv.date, prefs)} · balance {inv.balance_due ? formatMoney(inv.balance_due, "NAD") : "—"}
                  </span>
                </span>
                <PdfLink href={`/portal/invoices/${inv.id}/pdf`} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {job.inspections.length ? (
        <Panel title="Inspection reports" flush>
          <ul className="divide-y divide-border">
            {job.inspections.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
                <span>
                  {r.number}
                  <span className="block text-xs text-muted">{formatDate(r.date, prefs)}</span>
                </span>
                <PdfLink href={`/portal/inspections/${r.id}/pdf`} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
