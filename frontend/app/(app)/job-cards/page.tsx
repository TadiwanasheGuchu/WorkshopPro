import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { JobStatusBadge, OverdueBadge } from "@/components/app/job-status-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { JobCardSummary, JobStatus, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { JOB_STATUS_LABEL, PRIORITY_LABEL } from "@/lib/job-status";
import { vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Job cards" };

const VIEWS = {
  open: { label: "Open", params: { open_only: true } },
  mine: { label: "Assigned to me", params: { assigned_to_me: true, open_only: true } },
  overdue: { label: "Overdue", params: { overdue: true } },
  all: { label: "All", params: {} },
} as const;
type View = keyof typeof VIEWS;

export default function JobCardsPage({ searchParams }: PageProps<"/job-cards">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/job-cards">["searchParams"] }) {
  const me = await requireMe();
  const canView = canInAnyBranch(me, P.JOB_CARDS_VIEW);
  const canWork = canInAnyBranch(me, P.JOB_CARDS_WORK);
  if (!canView && !canWork) return <NoAccess />;

  const params = await searchParams;
  const defaultView: View = canView ? "open" : "mine";
  const view: View = typeof params.view === "string" && params.view in VIEWS ? (params.view as View) : defaultView;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const status = typeof params.status === "string" && params.status in JOB_STATUS_LABEL ? (params.status as JobStatus) : undefined;
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<JobCardSummary>>(
    `/job-cards${query({ ...VIEWS[view].params, status, search, page, page_size: 25 })}`,
  );
  const prefs = me.organisation;
  const tabs = (Object.keys(VIEWS) as View[])
    .filter((v) => canView || v === "mine")
    .filter((v) => canWork || v !== "mine")
    .map((v) => ({ href: v === defaultView ? "/job-cards" : `/job-cards?view=${v}`, label: VIEWS[v].label }));
  const activeHref = view === defaultView ? "/job-cards" : `/job-cards?view=${view}`;

  return (
    <>
      <PageHeader
        title="Job cards"
        actions={
          canInAnyBranch(me, P.JOB_CARDS_CREATE) ? (
            <Button asChild variant="primary">
              <Link href="/job-cards/new">Receive vehicle</Link>
            </Button>
          ) : null
        }
      />
      {tabs.length > 1 ? <TabNav tabs={tabs} active={status ? "" : activeHref} /> : null}
      {status ? (
        <p className="mb-3 text-sm">
          Showing <JobStatusBadge status={status} />{" "}
          <Link href="/job-cards" className="ml-2 text-steel hover:underline">
            Show all open jobs
          </Link>
        </p>
      ) : null}
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        {view !== defaultView ? <input type="hidden" name="view" value={view} /> : null}
        <label htmlFor="job-search" className="sr-only">
          Search job cards
        </label>
        <Input id="job-search" name="search" type="search" defaultValue={search} placeholder="Job number, registration or customer" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>

      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={search ? `No job cards match "${search}"` : view === "mine" ? "No jobs assigned to you" : "No job cards"} />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((j) => (
              <li key={j.id}>
                <Link
                  href={`/job-cards/${j.id}`}
                  className="grid gap-1.5 px-4 py-3 hover:bg-mist md:grid-cols-[8rem_1fr_13rem_10rem] md:items-center md:gap-4"
                >
                  <div className="flex items-center justify-between gap-2 md:block">
                    <span className="font-mono font-medium text-steel">{j.job_number}</span>
                    <span className="md:hidden">
                      <JobStatusBadge status={j.status} />
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate">
                      <span className="font-mono font-medium">{vehicleTitle(j.vehicle)}</span>
                      <span className="text-muted"> · {j.vehicle.make} {j.vehicle.model} · {j.customer.name}</span>
                    </p>
                    <p className="truncate text-sm text-muted">{j.complaint}</p>
                  </div>
                  <div className="hidden flex-wrap items-center gap-1.5 md:flex">
                    <JobStatusBadge status={j.status} />
                    {j.is_overdue ? <OverdueBadge /> : null}
                    {j.priority === "urgent" || j.priority === "high" ? (
                      <StatusBadge tone={j.priority === "urgent" ? "danger" : "waiting"}>{PRIORITY_LABEL[j.priority]}</StatusBadge>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-between gap-2 text-xs text-muted md:block md:text-right">
                    <span>{j.assignees.map((a) => a.name).join(", ") || "Unassigned"}</span>
                    <span className="block tabular-nums">
                      {j.promised_at ? `Due ${formatDateTime(j.promised_at, prefs)}` : `In ${formatDateTime(j.received_at, prefs)}`}
                    </span>
                    <span className="flex gap-1.5 md:hidden">
                      {j.is_overdue ? <OverdueBadge /> : null}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            hrefFor={(p) => `/job-cards${query({ view: view === defaultView ? undefined : view, status, search, page: p })}`}
          />
        </div>
      </Panel>
    </>
  );
}
