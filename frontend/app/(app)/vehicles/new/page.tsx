import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { CustomerDetail } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, canInAnyBranch } from "@/lib/permissions";

import { VehicleForm } from "../vehicle-form";

export const metadata: Metadata = { title: "Register vehicle" };

export default function NewVehiclePage({ searchParams }: PageProps<"/vehicles/new">) {
  return (
    <>
      <PageHeader title="Register vehicle" back={{ href: "/vehicles", label: "Vehicles" }} />
      <Suspense fallback={<PanelSkeleton rows={8} />}>
        <Content searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/vehicles/new">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.VEHICLES_MANAGE)) return <NoAccess />;
  const { customer_id } = await searchParams;
  const customer =
    typeof customer_id === "string" && /^[0-9a-f-]{36}$/.test(customer_id)
      ? await apiGet<CustomerDetail>(`/customers/${customer_id}`)
      : null;
  return (
    <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
      <VehicleForm customer={customer ? { id: customer.id, display_name: customer.display_name } : null} />
    </div>
  );
}
