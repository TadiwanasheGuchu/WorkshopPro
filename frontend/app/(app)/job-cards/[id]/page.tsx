import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { JobStatusBadge, OverdueBadge } from "@/components/app/job-status-badge";
import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { JobCardDetail, Quotation } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { EXCEPTION_TYPE_LABEL, FUEL_LEVEL_LABEL, JOB_STATUS_LABEL, PRIORITY_LABEL } from "@/lib/job-status";
import { formatKm, vehicleTitle } from "@/lib/labels";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import {
  AddNote,
  Assignments,
  AuthoriseExceptionButton,
  EditDetailsButton,
  RevokeExceptionButton,
  StatusActions,
  WorkRecord,
} from "./job-actions";
import { InspectionList, StartInspectionButton } from "./inspections-panel";
import { PrepareQuotationButton, QuotationSummary } from "./quotation-panel";

export const metadata: Metadata = { title: "Job card" };

export default function JobCardPage({ params }: PageProps<"/job-cards/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/job-cards/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.JOB_CARDS_VIEW) && !canInAnyBranch(me, P.JOB_CARDS_WORK)) return <NoAccess />;
  const { id } = await params;
  const job = await apiGet<JobCardDetail>(`/job-cards/${id}`);
  const prefs = me.organisation;
  const caps = job.capabilities;
  const activeExceptions = job.approval_exceptions.filter((e) => !e.revoked_at);
  const canPerform = can(me, P.INSPECTIONS_PERFORM, job.branch.id);
  const canViewQuotes = can(me, P.QUOTATIONS_VIEW, job.branch.id);
  const quote = canViewQuotes ? await apiGet<Quotation | null>(`/job-cards/${job.id}/quotation`) : null;

  return (
    <>
      <PageHeader
        title={job.job_number}
        description={
          <>
            <span className="font-mono">{vehicleTitle(job.vehicle)}</span> · {job.vehicle.make} {job.vehicle.model} ·{" "}
            {job.customer.name}
          </>
        }
        back={{ href: "/job-cards", label: "Job cards" }}
        actions={
          <div className="flex flex-wrap items-center gap-1.5">
            <JobStatusBadge status={job.status} />
            {job.is_overdue ? <OverdueBadge /> : null}
            {job.priority !== "normal" ? (
              <StatusBadge tone={job.priority === "urgent" ? "danger" : job.priority === "high" ? "waiting" : "neutral"}>
                {PRIORITY_LABEL[job.priority]} priority
              </StatusBadge>
            ) : null}
          </div>
        }
      />

      {caps.transitions.length ? (
        <section aria-label="Next actions" className="mb-5 rounded-panel border border-border bg-surface p-4">
          <StatusActions job={job} />
        </section>
      ) : null}

      {job.status === "completed" ? (
        <Alert tone="success" title={`Collected ${formatDateTime(job.collected_at, prefs)} by ${job.collected_by_name}`} className="mb-5">
          {job.handover_notes}
        </Alert>
      ) : null}
      {job.status === "cancelled" ? (
        <Alert tone="info" title="Job cancelled" className="mb-5">
          {job.cancellation_reason}
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <Panel title="Customer complaint" actions={caps.edit_details ? <EditDetailsButton job={job} /> : null}>
            <p className="whitespace-pre-line">{job.complaint}</p>
            {job.requested_work ? (
              <div className="mt-3 border-t border-border pt-3">
                <p className="text-xs text-muted">Requested work</p>
                <p className="whitespace-pre-line">{job.requested_work}</p>
              </div>
            ) : null}
          </Panel>

          <Panel
            title="Inspections"
            flush
            actions={
              canPerform && !["completed", "cancelled"].includes(job.status) ? (
                <StartInspectionButton jobId={job.id} hasIntake={job.inspections.some((i) => i.kind === "intake")} />
              ) : null
            }
          >
            <InspectionList inspections={job.inspections} />
          </Panel>

          <Panel title="Work record">
            <WorkRecord key={job.version} job={job} />
          </Panel>

          {canViewQuotes ? (
            <Panel
              title="Quotation"
              flush
              actions={
                !quote && can(me, P.QUOTATIONS_MANAGE, job.branch.id) && !["completed", "cancelled"].includes(job.status) ? (
                  <PrepareQuotationButton jobId={job.id} />
                ) : null
              }
            >
              {quote ? <QuotationSummary quote={quote} /> : <p className="px-4 py-3 text-sm text-muted">No quotation yet.</p>}
            </Panel>
          ) : null}

          <Panel
            title="Customer approval"
            description="Chargeable work needs an approved quotation or an authorised exception."
            actions={caps.authorise_exception ? <AuthoriseExceptionButton job={job} currency={prefs.currency_code} /> : null}
            flush
          >
            <div className="px-4 py-3">
              {job.approval_status === "quotation_approved" ? (
                <StatusBadge tone="success">Quotation approved by customer</StatusBadge>
              ) : job.approval_status === "exception_active" ? (
                <StatusBadge tone="success">Work authorised by exception</StatusBadge>
              ) : job.approval_status === "missing" ? (
                <StatusBadge tone="danger">No approval on record</StatusBadge>
              ) : (
                <StatusBadge tone="neutral">Not yet approved</StatusBadge>
              )}
            </div>
            {job.approval_exceptions.length ? (
              <ul className="divide-y divide-border border-t border-border">
                {job.approval_exceptions.map((e) => (
                  <li key={e.id} className="px-4 py-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <p className={e.revoked_at ? "font-medium text-muted line-through" : "font-medium"}>
                        {EXCEPTION_TYPE_LABEL[e.exception_type]}
                      </p>
                      {!e.revoked_at && caps.authorise_exception ? <RevokeExceptionButton jobId={job.id} exceptionId={e.id} /> : null}
                    </div>
                    <p>
                      <span className="text-muted">Authorised work:</span> {e.scope}
                    </p>
                    <p>
                      <span className="text-muted">Reason:</span> {e.reason}
                    </p>
                    {e.customer_contact ? (
                      <p>
                        <span className="text-muted">Customer contact:</span> {e.customer_contact}
                      </p>
                    ) : null}
                    {e.max_amount ? (
                      <p>
                        <span className="text-muted">Limit:</span>{" "}
                        <span className="font-mono tabular-nums">{formatMoney(e.max_amount, e.currency_code)}</span>
                      </p>
                    ) : null}
                    <p className="mt-1 text-xs text-muted">
                      {e.authorised_by} · {formatDateTime(e.authorised_at, prefs)}
                      {e.revoked_at ? ` · Revoked by ${e.revoked_by} (${e.revoke_reason})` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
            {activeExceptions.length === 0 && job.approval_status === "missing" ? (
              <p className="border-t border-border px-4 py-3 text-sm text-status-danger">
                Work is in progress without an active approval. Record the customer&apos;s approval.
              </p>
            ) : null}
          </Panel>

          <Panel title="Notes" flush>
            {job.notes.length === 0 ? <p className="px-4 py-3 text-sm text-muted">No notes yet.</p> : null}
            <ol className="divide-y divide-border">
              {job.notes.map((n) => (
                <li key={n.id} className="px-4 py-3">
                  <p className="text-sm whitespace-pre-line">{n.body}</p>
                  <p className="mt-1 flex items-center gap-2 text-xs text-muted">
                    {n.author ?? "System"} · {formatDateTime(n.created_at, prefs)}
                    {n.visibility === "customer" ? <StatusBadge tone="neutral">Customer visible</StatusBadge> : null}
                  </p>
                </li>
              ))}
            </ol>
            {caps.add_notes ? <AddNote jobId={job.id} /> : null}
          </Panel>
        </div>

        <div className="space-y-5">
          <Panel title="Mechanics">
            <Assignments job={job} />
          </Panel>

          <Panel title="Vehicle">
            <DetailList
              items={[
                {
                  label: "Vehicle",
                  value: (
                    <Link href={`/vehicles/${job.vehicle.id}`} className="font-mono text-steel hover:underline">
                      {vehicleTitle(job.vehicle)}
                    </Link>
                  ),
                },
                {
                  label: "Customer",
                  value: (
                    <Link href={`/customers/${job.customer.id}`} className="text-steel hover:underline">
                      {job.customer.name}
                    </Link>
                  ),
                },
                { label: "Odometer in", value: job.intake_odometer_km != null ? <span className="font-mono">{formatKm(job.intake_odometer_km)}</span> : null },
                { label: "Fuel in", value: job.fuel_level ? FUEL_LEVEL_LABEL[job.fuel_level] : null },
                { label: "Received", value: `${formatDateTime(job.received_at, prefs)}${job.received_by ? ` · ${job.received_by}` : ""}` },
                { label: "Promised", value: formatDateTime(job.promised_at, prefs) },
                { label: "Branch", value: job.branch.name },
                { label: "Bay", value: job.service_bay?.name },
              ]}
            />
          </Panel>

          <Panel title="Status history" flush>
            <ol className="divide-y divide-border">
              {[...job.status_history].reverse().map((h, i) => (
                <li key={`${h.changed_at}-${i}`} className="px-4 py-2.5 text-sm">
                  <p className="font-medium">{JOB_STATUS_LABEL[h.to_status]}</p>
                  {h.note ? <p className="text-sm">{h.note}</p> : null}
                  <p className="text-xs text-muted tabular-nums">
                    {formatDateTime(h.changed_at, prefs)}
                    {h.changed_by ? ` · ${h.changed_by}` : ""}
                  </p>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </>
  );
}
