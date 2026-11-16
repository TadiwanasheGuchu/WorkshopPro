import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, Payment } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { PAYMENT_KIND, PAYMENT_METHOD } from "@/lib/invoice";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Payments" };

const FILTERS = [
  { key: "all", label: "All" },
  { key: "payment", label: "Payments received" },
  { key: "refund", label: "Refunds" },
  { key: "reversal", label: "Reversals" },
] as const;

export default function PaymentsPage({ searchParams }: PageProps<"/payments">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/payments">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVOICES_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const kind = FILTERS.find((f) => f.key === params.kind && f.key !== "all")?.key;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<Payment>>(`/payments${query({ kind, search, page, page_size: 25 })}`);
  const prefs = me.organisation;

  return (
    <>
      <PageHeader title="Payments" description="Money received and paid back. Payments are recorded from an invoice; no card is charged." />
      <TabNav tabs={FILTERS.map((f) => ({ href: f.key === "all" ? "/payments" : `/payments?kind=${f.key}`, label: f.label }))} active={kind ? `/payments?kind=${kind}` : "/payments"} />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        {kind ? <input type="hidden" name="kind" value={kind} /> : null}
        <label htmlFor="payment-search" className="sr-only">
          Search payments
        </label>
        <Input id="payment-search" name="search" type="search" defaultValue={search} placeholder="Receipt number, reference or customer" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No payments recorded" />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((p) => (
              <li key={p.id}>
                <Link href={`/payments/${p.id}`} className="grid gap-1 px-4 py-3 hover:bg-mist sm:grid-cols-[9rem_1fr_12rem_9rem] sm:items-center">
                  <span className="font-mono font-medium text-steel">{p.receipt_number}</span>
                  <span className="min-w-0 truncate text-sm">
                    {p.customer.name}
                    <span className="block text-xs text-muted">
                      {PAYMENT_KIND[p.kind]} · {PAYMENT_METHOD[p.method]}
                      {p.reference ? ` · ${p.reference}` : ""}
                    </span>
                  </span>
                  <span className="text-sm text-muted">{formatDateTime(p.received_at, prefs)}</span>
                  <span className="flex items-center gap-2 font-mono text-sm tabular-nums sm:justify-end">
                    {p.reversed_by_receipt ? <StatusBadge tone="danger">Reversed</StatusBadge> : null}
                    {p.kind === "payment" ? "" : "−"}
                    {formatMoney(p.amount, p.currency_code)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(n) => `/payments${query({ kind, search, page: n })}`} />
        </div>
      </Panel>
    </>
  );
}
