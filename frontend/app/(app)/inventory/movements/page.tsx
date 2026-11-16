import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { MovementKind, Page, StockMovement } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { MOVEMENT_LABEL, qty, signedQty } from "@/lib/inventory";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Stock movements" };

const FILTERS: { key: MovementKind | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "adjustment", label: "Adjustments" },
  { key: "opening", label: "Opening stock" },
  { key: "transfer_out", label: "Transfers" },
  { key: "receipt", label: "Received" },
  { key: "issue", label: "Issued to jobs" },
];

export default function MovementsPage({ searchParams }: PageProps<"/inventory/movements">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/inventory/movements">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVENTORY_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const kind = FILTERS.find((f) => f.key === params.kind && f.key !== "all")?.key;
  const part = typeof params.part === "string" && /^[0-9a-f-]{36}$/.test(params.part) ? params.part : undefined;
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<StockMovement>>(`/inventory/movements${query({ kind, part_id: part, page, page_size: 50 })}`);
  const prefs = me.organisation;
  const showCost = data.items.some((m) => m.unit_cost !== null);

  return (
    <>
      <PageHeader title="Stock movements" description="Every change to stock, newest first. Movements cannot be edited; corrections are new movements." />
      <TabNav tabs={FILTERS.map((f) => ({ href: `/inventory/movements${query({ kind: f.key === "all" ? undefined : f.key, part })}`, label: f.label }))} active={`/inventory/movements${query({ kind, part })}`} />
      {part && data.items[0] ? (
        <p className="mb-3 text-sm">
          Showing <span className="font-mono">{data.items[0].sku}</span> only.{" "}
          <Link href={`/inventory/movements${query({ kind })}`} className="text-steel hover:underline">
            Show all parts
          </Link>
        </p>
      ) : null}
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No stock movements" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-sm">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">When</th>
                  <th className="px-4 py-2 text-left font-medium">Part</th>
                  <th className="px-4 py-2 text-left font-medium">Movement</th>
                  <th className="px-4 py-2 text-left font-medium">Location</th>
                  <th className="px-4 py-2 text-right font-medium">Qty</th>
                  <th className="px-4 py-2 text-right font-medium">Balance</th>
                  {showCost ? <th className="px-4 py-2 text-right font-medium">Unit cost</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((m) => (
                  <tr key={m.id} className="align-top">
                    <td className="px-4 py-2 whitespace-nowrap">
                      {formatDateTime(m.created_at, prefs)}
                      <span className="block text-xs text-muted">{m.created_by}</span>
                    </td>
                    <td className="px-4 py-2">
                      <Link href={`/inventory/parts/${m.part.id}`} className="font-mono text-steel hover:underline">
                        {m.sku}
                      </Link>
                      <span className="block text-xs text-muted">{m.part.name}</span>
                    </td>
                    <td className="px-4 py-2">
                      {MOVEMENT_LABEL[m.kind]}
                      {m.job_card ? (
                        <Link href={`/job-cards/${m.job_card.id}`} className="ml-1 font-mono text-steel hover:underline">
                          {m.job_card.name}
                        </Link>
                      ) : null}
                      {m.reason ? <span className="block text-xs text-muted">{m.reason}</span> : null}
                    </td>
                    <td className="px-4 py-2">
                      {m.location.name}
                      <span className="block text-xs text-muted">{m.branch.name}</span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{signedQty(m.quantity)}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{qty(m.balance_after)}</td>
                    {showCost ? <td className="px-4 py-2 text-right font-mono tabular-nums">{m.unit_cost ?? "—"}</td> : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(n) => `/inventory/movements${query({ kind, part, page: n })}`} />
        </div>
      </Panel>
    </>
  );
}
