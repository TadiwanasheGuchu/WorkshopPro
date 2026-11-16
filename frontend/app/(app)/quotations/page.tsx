import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, QuotationListItem, QuoteStatus } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";
import { QUOTE_STATUS } from "@/lib/quotation";

export const metadata: Metadata = { title: "Quotations" };

const FILTERS: { key: QuoteStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "sent", label: "Awaiting customer" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "expired", label: "Expired" },
];

export default function QuotationsPage({ searchParams }: PageProps<"/quotations">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/quotations">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.QUOTATIONS_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const status = FILTERS.find((f) => f.key === params.status && f.key !== "all")?.key;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<QuotationListItem>>(`/quotations${query({ status, search, page, page_size: 25 })}`);

  return (
    <>
      <PageHeader title="Quotations" description="Quotations are prepared from a job card." />
      <TabNav tabs={FILTERS.map((f) => ({ href: f.key === "all" ? "/quotations" : `/quotations?status=${f.key}`, label: f.label }))} active={status ? `/quotations?status=${status}` : "/quotations"} />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        {status ? <input type="hidden" name="status" value={status} /> : null}
        <label htmlFor="quote-search" className="sr-only">
          Search quotations
        </label>
        <Input id="quote-search" name="search" type="search" defaultValue={search} placeholder="Quote number or customer" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No quotations">
            <Link href="/job-cards" className="text-steel hover:underline">
              Open a job card to prepare one
            </Link>
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((q) => (
              <li key={q.id}>
                <Link href={`/quotations/${q.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[10rem_1fr_9rem_8rem] sm:items-center">
                  <span className="font-mono font-medium text-steel">
                    {q.quote_number}
                    {q.version_number > 1 ? <span className="text-xs text-muted"> v{q.version_number}</span> : null}
                  </span>
                  <span className="min-w-0 truncate text-sm">
                    {q.customer.name} · <span className="font-mono">{vehicleTitle(q.vehicle)}</span> · <span className="font-mono">{q.job_card.name}</span>
                  </span>
                  <span className="font-mono text-sm tabular-nums sm:text-right">{formatMoney(q.total, q.currency_code)}</span>
                  <span className="flex items-center gap-2 sm:justify-end">
                    <StatusBadge tone={QUOTE_STATUS[q.status].tone}>{QUOTE_STATUS[q.status].label}</StatusBadge>
                    <span className="text-xs text-muted sm:hidden">{formatDate(q.updated_at, me.organisation)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(p) => `/quotations${query({ status, search, page: p })}`} />
        </div>
      </Panel>
    </>
  );
}
