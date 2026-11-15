import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { EmptyState, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Branch, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Branches" };

export default function BranchesPage({ searchParams }: PageProps<"/branches">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={4} />}>
      <BranchesContent searchParams={searchParams} />
    </Suspense>
  );
}

async function BranchesContent({ searchParams }: { searchParams: PageProps<"/branches">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.BRANCHES_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const showArchived = params.archived === "1";
  const data = await apiGet<Page<Branch>>(`/branches${query({ include_archived: showArchived || undefined, page_size: 100 })}`);

  return (
    <>
      <PageHeader
        title="Branches"
        actions={
          can(me, P.BRANCHES_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/branches/new">Add branch</Link>
            </Button>
          ) : null
        }
      />
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No branches" />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((b) => (
              <li key={b.id}>
                <Link href={`/branches/${b.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
                  <div className="min-w-0">
                    <p className="font-medium text-steel">{b.name}</p>
                    <p className="truncate text-sm text-muted">
                      {[b.city, b.phone].filter(Boolean).join(" · ") || "No contact details"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {b.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                    <span className="font-mono text-sm text-muted">{b.code}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <p className="mt-3 text-sm">
        <Link href={showArchived ? "/branches" : "/branches?archived=1"} className="text-steel hover:underline">
          {showArchived ? "Hide archived branches" : "Show archived branches"}
        </Link>
      </p>
    </>
  );
}
