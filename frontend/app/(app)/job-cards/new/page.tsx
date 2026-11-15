import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Vehicle } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { ReceiveForm } from "./receive-form";

export const metadata: Metadata = { title: "Receive vehicle" };

export default function ReceiveVehiclePage({ searchParams }: PageProps<"/job-cards/new">) {
  return (
    <>
      <PageHeader title="Receive vehicle" description="Opens a job card with the next job number." back={{ href: "/job-cards", label: "Job cards" }} />
      <Suspense fallback={<PanelSkeleton rows={8} />}>
        <Content searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/job-cards/new">["searchParams"] }) {
  const me = await requireMe();
  const branches = me.branches.filter((b) => can(me, P.JOB_CARDS_CREATE, b.id));
  if (!branches.length) return <NoAccess />;
  const { vehicle_id } = await searchParams;
  const vehicle =
    typeof vehicle_id === "string" && /^[0-9a-f-]{36}$/.test(vehicle_id) ? await apiGet<Vehicle>(`/vehicles/${vehicle_id}`) : null;
  return (
    <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
      <ReceiveForm branches={branches} initialVehicle={vehicle} />
    </div>
  );
}
