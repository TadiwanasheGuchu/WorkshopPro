import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { BranchDetail, ServiceBay } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { ArchiveBranch, BranchForm, OperatingHoursForm, ServiceBays } from "../branch-forms";

export const metadata: Metadata = { title: "Branch" };

export default function BranchPage({ params }: PageProps<"/branches/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <BranchContent params={params} />
    </Suspense>
  );
}

async function BranchContent({ params }: { params: PageProps<"/branches/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.BRANCHES_VIEW)) return <NoAccess />;
  const { id } = await params;
  if (!can(me, P.BRANCHES_VIEW, id)) return <NoAccess />;

  const [branch, bays] = await Promise.all([
    apiGet<BranchDetail>(`/branches/${id}`),
    apiGet<ServiceBay[]>(`/branches/${id}/service-bays`),
  ]);
  const canEdit = can(me, P.BRANCHES_MANAGE, id) && !branch.archived_at;
  // Archiving is organisation-wide only.
  const canArchive = can(me, P.BRANCHES_MANAGE);

  return (
    <>
      <PageHeader
        title={branch.name}
        description={<span className="font-mono">{branch.code}</span>}
        back={{ href: "/branches", label: "Branches" }}
        actions={branch.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
      />
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Details" className="xl:col-span-2">
          <BranchForm branch={branch} readOnly={!canEdit} />
        </Panel>
        <Panel title="Operating hours" description="Used for bookings and due dates.">
          <OperatingHoursForm branchId={branch.id} hours={branch.operating_hours} readOnly={!canEdit} />
        </Panel>
        <Panel title="Service bays" description="Lifts, pits and work areas." flush>
          <ServiceBays branchId={branch.id} bays={bays} readOnly={!canEdit} />
        </Panel>
        {canArchive ? (
          <Panel title="Archive" className="xl:col-span-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted">
                {branch.archived_at
                  ? "This branch is archived. Restore it to use it again."
                  : "Archive a branch that has closed. Its records are kept."}
              </p>
              <ArchiveBranch branch={branch} />
            </div>
          </Panel>
        ) : null}
      </div>
    </>
  );
}
