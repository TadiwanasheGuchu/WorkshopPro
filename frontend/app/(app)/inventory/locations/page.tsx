import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { StockLocation } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { qty } from "@/lib/inventory";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { AddLocationButton, LocationActions } from "./location-actions";

export const metadata: Metadata = { title: "Stock locations" };

export default function LocationsPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.INVENTORY_VIEW)) return <NoAccess />;
  const locations = await apiGet<StockLocation[]>("/inventory/locations");
  const adjustable = me.branches.filter((b) => can(me, P.INVENTORY_ADJUST, b.id));

  return (
    <>
      <PageHeader
        title="Stock locations"
        description="Where parts are kept. Each branch has a default store; add shelves, stores or vans as needed."
        actions={adjustable.length ? <AddLocationButton branches={adjustable} /> : null}
      />
      <Panel flush>
        <ul className="divide-y divide-border">
          {locations.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div>
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {l.name}
                  {l.is_default ? <StatusBadge tone="neutral">Default</StatusBadge> : null}
                  {l.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                </p>
                <p className="text-sm text-muted">
                  {l.branch.name} · {l.part_count} {l.part_count === 1 ? "part" : "parts"} in stock · <span className="font-mono">{qty(l.units_on_hand)}</span> units
                </p>
              </div>
              {can(me, P.INVENTORY_ADJUST, l.branch.id) ? <LocationActions location={l} /> : null}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
