import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { CustomerSummary, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatPhone } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Customers" };

export default function CustomersPage({ searchParams }: PageProps<"/customers">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/customers">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.CUSTOMERS_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const archived = params.archived === "1";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<CustomerSummary>>(
    `/customers${query({ search, include_archived: archived || undefined, page, page_size: 25 })}`,
  );

  return (
    <>
      <PageHeader
        title="Customers"
        actions={
          canInAnyBranch(me, P.CUSTOMERS_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/customers/new">Register customer</Link>
            </Button>
          ) : null
        }
      />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="customer-search" className="sr-only">
          Search customers
        </label>
        <Input
          id="customer-search"
          name="search"
          type="search"
          defaultValue={search}
          placeholder="Name, phone, email or registration"
          className="sm:max-w-sm"
        />
        {archived ? <input type="hidden" name="archived" value="1" /> : null}
        <Button type="submit">Search</Button>
      </form>

      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={search ? `No customers match "${search}"` : "No customers yet"}>
            {search && canInAnyBranch(me, P.CUSTOMERS_MANAGE) ? (
              <Link href="/customers/new" className="text-steel hover:underline">
                Register a new customer
              </Link>
            ) : null}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((c) => (
              <li key={c.id}>
                <Link href={`/customers/${c.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[1fr_12rem_6rem] sm:items-center">
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 font-medium text-steel">
                      {c.display_name}
                      {c.customer_type === "company" ? <span className="text-xs font-normal text-muted">Company</span> : null}
                      {c.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                    </p>
                    {c.primary_email ? <p className="truncate text-xs text-muted">{c.primary_email}</p> : null}
                  </div>
                  <span className="font-mono text-sm">{formatPhone(c.primary_phone)}</span>
                  <span className="text-sm text-muted tabular-nums sm:text-right">
                    {c.vehicle_count} {c.vehicle_count === 1 ? "vehicle" : "vehicles"}
                  </span>
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
            hrefFor={(p) => `/customers${query({ search, archived: archived ? "1" : undefined, page: p })}`}
          />
        </div>
      </Panel>
      <p className="mt-3 text-sm">
        <Link href={archived ? "/customers" : "/customers?archived=1"} className="text-steel hover:underline">
          {archived ? "Hide archived customers" : "Include archived customers"}
        </Link>
      </p>
    </>
  );
}
