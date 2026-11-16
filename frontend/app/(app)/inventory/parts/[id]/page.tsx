import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, Part, StockLocation, StockMovement } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { MOVEMENT_LABEL, UNIT_LABEL, qty, signedQty } from "@/lib/inventory";
import { P, canInAnyBranch } from "@/lib/permissions";

import { AdjustButton, ArchivePartButton, MinLevelButton, TransferButton } from "./stock-actions";

export const metadata: Metadata = { title: "Part" };

export default function PartPage({ params }: PageProps<"/inventory/parts/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/inventory/parts/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVENTORY_VIEW)) return <NoAccess />;
  const { id } = await params;
  const [part, movements, locations] = await Promise.all([
    apiGet<Part>(`/inventory/parts/${id}`),
    apiGet<Page<StockMovement>>(`/inventory/movements${query({ part_id: id, page_size: 10 })}`),
    apiGet<StockLocation[]>("/inventory/locations"),
  ]);
  const prefs = me.organisation;
  const c = prefs.currency_code;
  const transferTargets = locations.filter((l) => !l.archived_at);

  return (
    <>
      <PageHeader
        title={`${part.sku} · ${part.name}`}
        back={{ href: "/inventory/parts", label: "Parts catalogue" }}
        actions={
          <span className="flex flex-wrap items-center gap-2">
            {part.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
            {part.stock.low_locations ? <StatusBadge tone="danger">Low stock</StatusBadge> : null}
            {part.capabilities.edit ? (
              <Button asChild>
                <Link href={`/inventory/parts/${part.id}/edit`}>Edit</Link>
              </Button>
            ) : null}
            {part.capabilities.archive ? <ArchivePartButton part={part} /> : null}
          </span>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <Panel title="Stock by location" flush>
            {part.levels.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">No stock locations in your branches.</p>
            ) : (
              <ul className="divide-y divide-border">
                {part.levels.map((lv) => (
                  <li key={lv.location.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
                    <div>
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                        {lv.location.name}
                        <span className="font-normal text-muted">{lv.branch.name}</span>
                        {lv.is_low ? <StatusBadge tone="danger">Low stock</StatusBadge> : null}
                      </p>
                      <p className="font-mono text-sm tabular-nums">
                        {qty(lv.on_hand)} on hand · {qty(lv.reserved)} reserved · <span className="font-semibold">{qty(lv.available)} available</span>
                        <span className="font-sans text-xs text-muted"> · minimum {lv.min_quantity !== null ? qty(lv.min_quantity) : "not set"}</span>
                      </p>
                    </div>
                    {!part.archived_at ? (
                      <div className="flex flex-wrap gap-2">
                        {lv.can_adjust ? <AdjustButton part={part} level={lv} /> : null}
                        {lv.can_transfer ? <TransferButton part={part} level={lv} locations={transferTargets} /> : null}
                        {lv.can_adjust ? <MinLevelButton part={part} level={lv} /> : null}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Recent movements"
            flush
            actions={
              movements.total > movements.items.length ? (
                <Link href={`/inventory/movements?part=${part.id}`} className="text-sm text-steel hover:underline">
                  All {movements.total}
                </Link>
              ) : null
            }
          >
            {movements.items.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">No stock recorded yet. Use Count / adjust to load opening stock.</p>
            ) : (
              <ul className="divide-y divide-border">
                {movements.items.map((m) => (
                  <li key={m.id} className="flex items-start justify-between gap-3 px-4 py-2.5 text-sm">
                    <div>
                      <p>
                        {MOVEMENT_LABEL[m.kind]} · {m.location.name}
                        {m.job_card ? (
                          <>
                            {" · "}
                            <Link href={`/job-cards/${m.job_card.id}`} className="font-mono text-steel hover:underline">
                              {m.job_card.name}
                            </Link>
                          </>
                        ) : null}
                      </p>
                      <p className="text-xs text-muted">
                        {formatDateTime(m.created_at, prefs)} · {m.created_by}
                        {m.reason ? ` · ${m.reason}` : ""}
                      </p>
                    </div>
                    <span className="text-right font-mono tabular-nums">
                      {signedQty(m.quantity)}
                      <span className="block text-xs text-muted">bal. {qty(m.balance_after)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="Details">
          <DetailList
            items={[
              { label: "Category", value: part.category?.name },
              { label: "Unit", value: UNIT_LABEL[part.unit] },
              { label: "Selling price", value: <span className="font-mono">{formatMoney(part.selling_price, c)}</span> },
              ...(part.cost_price !== null ? [{ label: "Cost price", value: <span className="font-mono">{formatMoney(part.cost_price, c)}</span> }] : []),
              { label: "Tax", value: part.tax_rate?.name ?? "No tax" },
              { label: "Manufacturer", value: part.manufacturer },
              { label: "Manufacturer part number", value: part.manufacturer_part_number ? <span className="font-mono">{part.manufacturer_part_number}</span> : null },
            ]}
          />
          {part.description ? <p className="mt-4 text-sm whitespace-pre-line">{part.description}</p> : null}
        </Panel>
      </div>
    </>
  );
}
