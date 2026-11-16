import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { InvoiceListItem, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { invoiceStatus } from "@/lib/invoice";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Invoices" };

const FILTERS = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "outstanding", label: "Outstanding" },
  { key: "overdue", label: "Overdue" },
  { key: "paid", label: "Paid" },
] as const;

export default function InvoicesPage({ searchParams }: PageProps<"/invoices">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/invoices">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVOICES_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const status = FILTERS.find((f) => f.key === params.status && f.key !== "all")?.key;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<InvoiceListItem>>(`/invoices${query({ status, search, page, page_size: 25 })}`);
  const prefs = me.organisation;

  return (
    <>
      <PageHeader title="Invoices" description="Invoices are started from a job card once the work has passed quality inspection." />
      <TabNav tabs={FILTERS.map((f) => ({ href: f.key === "all" ? "/invoices" : `/invoices?status=${f.key}`, label: f.label }))} active={status ? `/invoices?status=${status}` : "/invoices"} />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        {status ? <input type="hidden" name="status" value={status} /> : null}
        <label htmlFor="invoice-search" className="sr-only">
          Search invoices
        </label>
        <Input id="invoice-search" name="search" type="search" defaultValue={search} placeholder="Invoice number, job number or customer" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No invoices">
            <Link href="/job-cards" className="text-steel hover:underline">
              Open a job card to start one
            </Link>
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            <li className="hidden px-4 py-2 text-xs text-muted sm:grid sm:grid-cols-[9rem_1fr_7rem_8rem_8rem_8rem]">
              <span>Number</span>
              <span>Customer · job</span>
              <span>Due</span>
              <span className="text-right">Total</span>
              <span className="text-right">Balance due</span>
              <span className="text-right">Status</span>
            </li>
            {data.items.map((i) => {
              const st = invoiceStatus(i);
              return (
                <li key={i.id}>
                  <Link href={`/invoices/${i.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[9rem_1fr_7rem_8rem_8rem_8rem] sm:items-center">
                    <span className="font-mono font-medium text-steel">{i.invoice_number ?? "Draft"}</span>
                    <span className="min-w-0 truncate text-sm">
                      {i.customer.name}
                      {i.job_card ? (
                        <>
                          {" · "}
                          <span className="font-mono">{i.job_card.name}</span>
                        </>
                      ) : null}
                    </span>
                    <span className="text-sm text-muted">{i.due_date ? formatDate(i.due_date, prefs) : "—"}</span>
                    <span className="font-mono text-sm tabular-nums sm:text-right">{formatMoney(i.total, i.currency_code)}</span>
                    <span className="font-mono text-sm tabular-nums sm:text-right">{i.status === "issued" ? formatMoney(i.balance_due, i.currency_code) : "—"}</span>
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
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(p) => `/invoices${query({ status, search, page: p })}`} />
        </div>
      </Panel>
    </>
  );
}
