import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Vehicle } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";

import { VehicleForm } from "../../vehicle-form";

export const metadata: Metadata = { title: "Edit vehicle" };

export default function EditVehiclePage({ params }: PageProps<"/vehicles/[id]/edit">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/vehicles/[id]/edit">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.VEHICLES_MANAGE)) return <NoAccess />;
  const { id } = await params;
  const vehicle = await apiGet<Vehicle>(`/vehicles/${id}`);
  return (
    <>
      <PageHeader title={`Edit ${vehicleTitle(vehicle)}`} back={{ href: `/vehicles/${id}`, label: vehicleTitle(vehicle) }} />
      <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
        <VehicleForm vehicle={vehicle} />
      </div>
    </>
  );
}
