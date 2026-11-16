import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, PartCategory, PartListItem } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatMoney } from "@/lib/format";
import { qty } from "@/lib/inventory";
import { P, can, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Parts catalogue" };

export default function PartsPage({ searchParams }: PageProps<"/inventory/parts">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/inventory/parts">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVENTORY_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const low = params.low === "1";
  const archived = params.archived === "1";
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const category = typeof params.category === "string" ? params.category : "";
  const page = Math.max(1, Number(params.page) || 1);
  const [data, categories] = await Promise.all([
    apiGet<Page<PartListItem>>(
      `/inventory/parts${query({ search, category_id: category || undefined, low_stock: low || undefined, include_archived: archived || undefined, page, page_size: 25 })}`,
    ),
    apiGet<PartCategory[]>("/inventory/categories"),
  ]);
  const currency = me.organisation.currency_code;
  const base = { search: search || undefined, category: category || undefined };

  return (
    <>
      <PageHeader
        title="Parts catalogue"
        actions={
          can(me, P.INVENTORY_CATALOGUE) ? (
            <Button asChild variant="primary">
              <Link href="/inventory/parts/new">Add part</Link>
            </Button>
          ) : null
        }
      />
      <TabNav
        tabs={[
          { href: `/inventory/parts${query(base)}`, label: "All parts" },
          { href: `/inventory/parts${query({ ...base, low: "1" })}`, label: "Low stock" },
          { href: `/inventory/parts${query({ ...base, archived: "1" })}`, label: "Including archived" },
        ]}
        active={`/inventory/parts${query({ ...base, low: low ? "1" : undefined, archived: archived ? "1" : undefined })}`}
      />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        {low ? <input type="hidden" name="low" value="1" /> : null}
        {archived ? <input type="hidden" name="archived" value="1" /> : null}
        <label htmlFor="part-search" className="sr-only">
          Search parts
        </label>
        <Input id="part-search" name="search" type="search" defaultValue={search} placeholder="SKU, name or manufacturer number" className="sm:max-w-sm" />
        {categories.length ? (
          <>
            <label htmlFor="part-category" className="sr-only">
              Category
            </label>
            <Select id="part-category" name="category" defaultValue={category} className="sm:max-w-48">
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </>
        ) : null}
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={low ? "No parts are low on stock" : "No parts"}>
            {!low && can(me, P.INVENTORY_CATALOGUE) ? (
              <Link href="/inventory/parts/new" className="text-steel hover:underline">
                Add the first part
              </Link>
            ) : null}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            <li className="hidden px-4 py-2 text-xs text-muted md:grid md:grid-cols-[10rem_1fr_8rem_6rem_6rem_8rem]">
              <span>SKU</span>
              <span>Part</span>
              <span>Category</span>
              <span className="text-right">On hand</span>
              <span className="text-right">Available</span>
              <span className="text-right">Price</span>
            </li>
            {data.items.map((p) => (
              <li key={p.id}>
                <Link href={`/inventory/parts/${p.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist md:grid-cols-[10rem_1fr_8rem_6rem_6rem_8rem] md:items-center">
                  <span className="font-mono font-medium text-steel">{p.sku}</span>
                  <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
                    <span className="truncate">{p.name}</span>
                    {p.stock.low_locations ? <StatusBadge tone="danger">Low stock</StatusBadge> : null}
                    {p.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                  </span>
                  <span className="text-sm text-muted">{p.category?.name ?? "—"}</span>
                  <span className="font-mono text-sm tabular-nums md:text-right">
                    <span className="text-muted md:hidden">On hand </span>
                    {qty(p.stock.on_hand)}
                  </span>
                  <span className="font-mono text-sm tabular-nums md:text-right">
                    <span className="text-muted md:hidden">Available </span>
                    {qty(p.stock.available)}
                  </span>
                  <span className="font-mono text-sm tabular-nums md:text-right">{formatMoney(p.selling_price, currency)}</span>
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
            hrefFor={(n) => `/inventory/parts${query({ ...base, low: low ? "1" : undefined, archived: archived ? "1" : undefined, page: n })}`}
          />
        </div>
      </Panel>
    </>
  );
}
