import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, PoListItem } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { P, canInAnyBranch } from "@/lib/permissions";
import { poStatus } from "@/lib/purchasing";

export const metadata: Metadata = { title: "Purchase orders" };

const FILTERS = [
  { key: "open", label: "Awaiting delivery" },
  { key: "draft", label: "Draft" },
  { key: "done", label: "Completed" },
  { key: "all", label: "All" },
] as const;

export default function PurchaseOrdersPage({ searchParams }: PageProps<"/purchase-orders">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/purchase-orders">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.SUPPLIERS_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const filter = FILTERS.find((f) => f.key === params.status)?.key ?? "open";
  const supplier = typeof params.supplier === "string" && /^[0-9a-f-]{36}$/.test(params.supplier) ? params.supplier : undefined;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<PoListItem>>(
    `/purchase-orders${query({ status: filter === "all" ? undefined : filter, supplier_id: supplier, search, page, page_size: 25 })}`,
  );
  const prefs = me.organisation;

  return (
    <>
      <PageHeader
        title="Purchase orders"
        description="Start an order from a supplier's page."
        actions={
          canInAnyBranch(me, P.PURCHASING_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/suppliers">Choose a supplier</Link>
            </Button>
          ) : null
        }
      />
      <TabNav tabs={FILTERS.map((f) => ({ href: `/purchase-orders${query({ status: f.key, supplier })}`, label: f.label }))} active={`/purchase-orders${query({ status: filter, supplier })}`} />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        <input type="hidden" name="status" value={filter} />
        <label htmlFor="po-search" className="sr-only">
          Search purchase orders
        </label>
        <Input id="po-search" name="search" type="search" defaultValue={search} placeholder="Order number or supplier" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={filter === "open" ? "Nothing awaiting delivery" : "No purchase orders"} />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((o) => {
              const st = poStatus(o);
              return (
                <li key={o.id}>
                  <Link href={`/purchase-orders/${o.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[9rem_1fr_8rem_9rem_9rem] sm:items-center">
                    <span className="font-mono font-medium text-steel">{o.po_number}</span>
                    <span className="min-w-0 truncate text-sm">
                      {o.supplier.name} <span className="text-muted">· {o.branch.name}</span>
                    </span>
                    <span className="text-sm text-muted">{o.expected_date ? `Due ${formatDate(o.expected_date, prefs)}` : "—"}</span>
                    <span className="font-mono text-sm tabular-nums sm:text-right">{formatMoney(o.total, o.currency_code)}</span>
                    <span className="sm:text-right">
                      <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(n) => `/purchase-orders${query({ status: filter, supplier, search, page: n })}`} />
        </div>
      </Panel>
    </>
  );
}
