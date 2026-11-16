import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, SupplierListItem } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Suppliers" };

export default function SuppliersPage({ searchParams }: PageProps<"/suppliers">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/suppliers">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.SUPPLIERS_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<SupplierListItem>>(`/suppliers${query({ search, page, page_size: 25 })}`);

  return (
    <>
      <PageHeader
        title="Suppliers"
        actions={
          can(me, P.SUPPLIERS_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/suppliers/new">Add supplier</Link>
            </Button>
          ) : null
        }
      />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="supplier-search" className="sr-only">
          Search suppliers
        </label>
        <Input id="supplier-search" name="search" type="search" defaultValue={search} placeholder="Name or contact" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No suppliers">
            {can(me, P.SUPPLIERS_MANAGE) ? (
              <Link href="/suppliers/new" className="text-steel hover:underline">
                Add your first supplier
              </Link>
            ) : null}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((s) => (
              <li key={s.id}>
                <Link href={`/suppliers/${s.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[1fr_14rem_8rem] sm:items-center">
                  <span className="flex items-center gap-2 font-medium text-steel">
                    {s.name}
                    {s.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                  </span>
                  <span className="text-sm text-muted">{[s.contact_person, s.phone].filter(Boolean).join(" · ") || "—"}</span>
                  <span className="text-sm sm:text-right">{s.open_orders ? `${s.open_orders} open ${s.open_orders === 1 ? "order" : "orders"}` : <span className="text-muted">No open orders</span>}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(n) => `/suppliers${query({ search, page: n })}`} />
        </div>
      </Panel>
    </>
  );
}
