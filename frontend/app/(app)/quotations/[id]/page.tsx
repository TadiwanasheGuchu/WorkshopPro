import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Quotation, TaxRate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";
import { DECISION_METHOD, QUOTE_STATUS } from "@/lib/quotation";

import { DraftEditor, SentActions } from "./quote-editor";
import { QuoteLines } from "./quote-lines";

export const metadata: Metadata = { title: "Quotation" };

export default function QuotationPage({ params }: PageProps<"/quotations/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/quotations/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.QUOTATIONS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const q = await apiGet<Quotation>(`/quotations/${id}`);
  const v = q.current;
  const editing = q.capabilities.edit;
  const taxRates = editing ? await apiGet<TaxRate[]>("/organisation/tax-rates") : [];
  const prefs = me.organisation;
  const st = QUOTE_STATUS[v.status];

  return (
    <>
      <PageHeader
        title={`${q.quote_number} · version ${v.version_number}`}
        description={
          <>
            <Link href={`/job-cards/${q.job_card.id}`} className="font-mono text-steel hover:underline">
              {q.job_card.name}
            </Link>{" "}
            · <span className="font-mono">{vehicleTitle(q.vehicle)}</span> · {q.customer.name}
          </>
        }
        back={{ href: "/quotations", label: "Quotations" }}
        actions={<StatusBadge tone={st.tone}>{st.label}</StatusBadge>}
      />

      {v.revision_reason ? (
        <Alert tone="info" className="mb-4">
          Revision: {v.revision_reason}
        </Alert>
      ) : null}
      {v.status === "expired" ? (
        <Alert tone="error" className="mb-4" title="This quotation has expired">
          Revise it to send an updated version to the customer.
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-5">
          <Panel title={editing ? "Lines" : "Quotation"}>
            {editing ? (
              <>
                {v.items.length ? (
                  <div className="mb-5 border-b border-border pb-5">
                    <QuoteLines version={v} />
                  </div>
                ) : null}
                <DraftEditor key={v.id + v.total + v.items.length} quote={q} taxRates={taxRates} />
              </>
            ) : (
              <>
                <QuoteLines version={v} />
                {v.notes ? <p className="mt-4 text-sm whitespace-pre-line">{v.notes}</p> : null}
                {v.terms ? (
                  <div className="mt-4 border-t border-border pt-3 text-xs whitespace-pre-line text-muted">{v.terms}</div>
                ) : null}
              </>
            )}
          </Panel>
          {!editing && (q.capabilities.record_decision || q.capabilities.revise) ? (
            <section aria-label="Actions" className="rounded-panel border border-border bg-surface p-4">
              <SentActions quote={q} />
            </section>
          ) : null}
        </div>

        <div className="space-y-5">
          {v.decision ? (
            <Panel title={v.decision.decision === "approved" ? "Customer approval" : "Customer rejection"}>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-xs text-muted">{v.decision.decision === "approved" ? "Approved" : "Rejected"} by</dt>
                  <dd>{v.decision.customer_name}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">For</dt>
                  <dd className="font-mono">
                    {formatMoney(v.decision.total, v.decision.currency_code)} (version {v.version_number})
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">How</dt>
                  <dd>{DECISION_METHOD[v.decision.method] ?? v.decision.method}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">When</dt>
                  <dd>{formatDateTime(v.decision.decided_at, prefs)}</dd>
                </div>
                {v.decision.evidence ? (
                  <div>
                    <dt className="text-xs text-muted">Evidence</dt>
                    <dd>{v.decision.evidence}</dd>
                  </div>
                ) : null}
                {v.decision.recorded_by ? (
                  <div>
                    <dt className="text-xs text-muted">Recorded by</dt>
                    <dd>{v.decision.recorded_by}</dd>
                  </div>
                ) : null}
                {v.decision.comments ? (
                  <div>
                    <dt className="text-xs text-muted">Customer comments</dt>
                    <dd className="whitespace-pre-line">{v.decision.comments}</dd>
                  </div>
                ) : null}
              </dl>
            </Panel>
          ) : null}

          {v.sent_at ? (
            <Panel title="Sent">
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-xs text-muted">Sent</dt>
                  <dd>
                    {formatDateTime(v.sent_at, prefs)}
                    {v.sent_by ? ` · ${v.sent_by}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Valid until</dt>
                  <dd>{formatDate(v.valid_until, prefs)}</dd>
                </div>
                {v.link ? (
                  <div>
                    <dt className="text-xs text-muted">Customer link</dt>
                    <dd>
                      {v.link.view_count
                        ? `Opened ${v.link.view_count} ${v.link.view_count === 1 ? "time" : "times"}, last ${formatDateTime(v.link.last_viewed_at, prefs)}`
                        : "Not opened yet"}
                      <p className="text-xs text-muted">Opening the link is not approval.</p>
                    </dd>
                  </div>
                ) : null}
              </dl>
            </Panel>
          ) : null}

          <Panel title="Versions" flush>
            <ol className="divide-y divide-border">
              {q.versions.map((ver) => (
                <li key={ver.id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
                  <span>Version {ver.version_number}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono tabular-nums">{formatMoney(ver.total, v.currency_code)}</span>
                    <StatusBadge tone={QUOTE_STATUS[ver.status].tone}>{QUOTE_STATUS[ver.status].label}</StatusBadge>
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </>
  );
}
