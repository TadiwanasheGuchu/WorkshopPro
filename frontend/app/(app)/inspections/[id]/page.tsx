import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { InspectionDetail } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { KIND_LABEL, RESULT_LABEL } from "@/lib/inspection";
import { vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";

import { Checklist } from "./checklist";

export const metadata: Metadata = { title: "Inspection" };

export default function InspectionPage({ params }: PageProps<"/inspections/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/inspections/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.JOB_CARDS_VIEW) && !canInAnyBranch(me, P.JOB_CARDS_WORK)) return <NoAccess />;
  const { id } = await params;
  const inspection = await apiGet<InspectionDetail>(`/inspections/${id}`);
  const prefs = me.organisation;
  const submitted = inspection.status === "submitted";

  return (
    <>
      <PageHeader
        title={KIND_LABEL[inspection.kind]}
        description={
          <>
            <span className="font-mono">{inspection.job_card.job_number}</span> ·{" "}
            <span className="font-mono">{vehicleTitle(inspection.vehicle)}</span> · {inspection.vehicle.make} {inspection.vehicle.model}
          </>
        }
        back={{ href: `/job-cards/${inspection.job_card.id}`, label: inspection.job_card.job_number }}
        actions={
          <StatusBadge tone={submitted ? "success" : "neutral"}>{submitted ? "Submitted" : "Draft"}</StatusBadge>
        }
      />
      {submitted ? (
        <p className="mb-4 text-sm text-muted">
          Submitted {formatDateTime(inspection.submitted_at, prefs)} by {inspection.submitted_by} ·{" "}
          {inspection.counts.fail} failed · {inspection.counts.attention} need attention · {inspection.counts.pass} passed
        </p>
      ) : null}
      <div className="max-w-3xl space-y-5">
        <Checklist key={`${inspection.status}-${inspection.amendments.length}`} inspection={inspection} />
        {inspection.amendments.length ? (
          <Panel title="Amendments" flush>
            <ul className="divide-y divide-border">
              {inspection.amendments.map((a, i) => (
                <li key={i} className="px-4 py-3 text-sm">
                  <p className="font-medium">{a.item_label}</p>
                  <p>
                    {RESULT_LABEL[a.old_result]} → {RESULT_LABEL[a.new_result]}
                  </p>
                  <p className="text-muted">Reason: {a.reason}</p>
                  <p className="text-xs text-muted">
                    {a.amended_by} · {formatDateTime(a.amended_at, prefs)}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}
      </div>
    </>
  );
}
