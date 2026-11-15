import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { BranchForm } from "../branch-forms";

export const metadata: Metadata = { title: "Add branch" };

export default function NewBranchPage() {
  return (
    <>
      <PageHeader
        title="Add branch"
        description="Default operating hours are applied; adjust them after creating the branch."
        back={{ href: "/branches", label: "Branches" }}
      />
      <Suspense fallback={<PanelSkeleton rows={5} />}>
        <NewBranchContent />
      </Suspense>
    </>
  );
}

async function NewBranchContent() {
  const me = await requireMe();
  if (!can(me, P.BRANCHES_MANAGE)) return <NoAccess />;
  return (
    <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
      <BranchForm />
    </div>
  );
}
