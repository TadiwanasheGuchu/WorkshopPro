import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuditList } from "@/components/app/audit-list";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { AuditLogEntry, Ownership, Page, Vehicle } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { FUEL_TYPE, TRANSMISSION, formatKm, vehicleTitle } from "@/lib/labels";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { ArchiveVehicleButton, TransferVehicleButton } from "./vehicle-actions";

export const metadata: Metadata = { title: "Vehicle" };

export default function VehiclePage({ params }: PageProps<"/vehicles/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/vehicles/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.VEHICLES_VIEW)) return <NoAccess />;
  const { id } = await params;
  const [v, owners, activity] = await Promise.all([
    apiGet<Vehicle>(`/vehicles/${id}`),
    apiGet<Ownership[]>(`/vehicles/${id}/ownership`),
    can(me, P.AUDIT_VIEW) ? apiGet<Page<AuditLogEntry>>(`/audit-logs?entity_type=vehicle&entity_id=${id}&page_size=8`) : Promise.resolve(null),
  ]);
  const manage = canInAnyBranch(me, P.VEHICLES_MANAGE);
  const prefs = me.organisation;

  return (
    <>
      <PageHeader
        title={vehicleTitle(v)}
        description={[v.year, v.make, v.model, v.variant].filter(Boolean).join(" ")}
        back={{ href: "/vehicles", label: "Vehicles" }}
        actions={
          <>
            {v.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
            {manage && !v.archived_at ? (
              <>
                <TransferVehicleButton vehicleId={v.id} currentOwnerId={v.customer.id} />
                <Button asChild>
                  <Link href={`/vehicles/${v.id}/edit`}>Edit</Link>
                </Button>
              </>
            ) : null}
          </>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <Panel title="Vehicle">
            <DetailList
              items={[
                {
                  label: "Owner",
                  value: (
                    <Link href={`/customers/${v.customer.id}`} className="text-steel hover:underline">
                      {v.customer.display_name}
                    </Link>
                  ),
                },
                { label: "Registration", value: v.registration_number ? <span className="font-mono">{v.registration_number}</span> : null },
                { label: "VIN / chassis", value: v.vin ? <span className="font-mono">{v.vin}</span> : null },
                { label: "Engine number", value: v.engine_number ? <span className="font-mono">{v.engine_number}</span> : null },
                { label: "Fuel", value: v.fuel_type ? FUEL_TYPE[v.fuel_type] : null },
                { label: "Transmission", value: v.transmission ? TRANSMISSION[v.transmission] : null },
                { label: "Colour", value: v.colour },
                {
                  label: "Odometer",
                  value: v.odometer_km != null ? (
                    <span className="font-mono tabular-nums">
                      {formatKm(v.odometer_km)}
                      <span className="font-sans text-xs text-muted"> · {formatDate(v.odometer_recorded_at, prefs)}</span>
                    </span>
                  ) : null,
                },
              ]}
            />
          </Panel>
          <Panel title="Existing damage">
            <p className="text-sm whitespace-pre-line">{v.existing_damage ?? <span className="text-muted">None recorded.</span>}</p>
            {v.notes ? <p className="mt-3 border-t border-border pt-3 text-sm whitespace-pre-line">{v.notes}</p> : null}
          </Panel>
          <Panel title="Service history">
            <p className="text-sm text-muted">Job cards and inspections for this vehicle appear here once those modules are in use.</p>
          </Panel>
        </div>
        <div className="space-y-5">
          <Panel title="Ownership history" flush>
            <ol className="divide-y divide-border">
              {owners.map((o) => (
                <li key={o.started_at} className="px-4 py-2.5 text-sm">
                  <Link href={`/customers/${o.customer.id}`} className="font-medium text-steel hover:underline">
                    {o.customer.display_name}
                  </Link>
                  <p className="text-xs text-muted tabular-nums">
                    {formatDate(o.started_at, prefs)} – {o.ended_at ? formatDate(o.ended_at, prefs) : "now"}
                    {o.note ? ` · ${o.note}` : ""}
                  </p>
                </li>
              ))}
            </ol>
          </Panel>
          {activity ? (
            <Panel title="Recent activity" flush>
              <AuditList entries={activity.items} me={me} />
            </Panel>
          ) : null}
          {manage ? (
            <Panel title="Archive">
              <ArchiveVehicleButton vehicleId={v.id} archived={Boolean(v.archived_at)} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
