import type { Metadata } from "next";
import Link from "next/link";

import { DocumentLines } from "@/components/app/document-lines";
import { PdfLink } from "@/components/app/pdf-link";
import { Alert } from "@/components/ui/alert";
import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { DateFormat, PortalMe, PortalQuotation } from "@/lib/api/types";
import { formatDate, formatDateTime } from "@/lib/format";

import { DecisionForm } from "./decision-form";

export const metadata: Metadata = { title: "Quotation" };

export default async function PortalQuotationPage({ params }: PageProps<"/portal/quotations/[id]">) {
  const { id } = await params;
  const [q, me] = await Promise.all([portalGet<PortalQuotation>(`/quotations/${id}`), portalGet<PortalMe>("/me")]);
  const prefs = { timezone: me.timezone, date_format: me.date_format as DateFormat };

  return (
    <div className="space-y-5">
      <div>
        <Link href="/portal" className="text-sm text-steel hover:underline">
          ← Overview
        </Link>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">
            Quotation <span className="font-mono">{q.quote_number}</span>
            {q.version_number > 1 ? <span className="text-sm font-normal text-muted"> (version {q.version_number})</span> : null}
          </h1>
          <PdfLink href={`/portal/quotations/${q.id}/pdf`} />
        </div>
        <p className="text-sm text-muted">
          {q.vehicle} · job <span className="font-mono">{q.job_number}</span>
          {q.valid_until ? ` · valid until ${formatDate(q.valid_until, prefs)}` : ""}
        </p>
      </div>
      {q.decision ? (
        <Alert tone={q.decision === "approved" ? "success" : "info"}>
          You {q.decision} this quotation{q.decided_at ? ` on ${formatDateTime(q.decided_at, prefs)}` : ""}.
        </Alert>
      ) : null}
      {q.status === "expired" ? <Alert tone="error">This quotation has expired. Contact the workshop for an updated one.</Alert> : null}
      <Panel title="Work and parts">
        <DocumentLines document={q} />
        {q.notes ? <p className="mt-4 text-sm whitespace-pre-line">{q.notes}</p> : null}
        {q.terms ? <p className="mt-4 border-t border-border pt-3 text-xs whitespace-pre-line text-muted">{q.terms}</p> : null}
      </Panel>
      {q.can_decide ? (
        <Panel title="Your decision">
          <DecisionForm id={q.id} />
        </Panel>
      ) : null}
    </div>
  );
}
