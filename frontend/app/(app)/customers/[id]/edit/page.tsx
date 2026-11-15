import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { CustomerDetail } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, canInAnyBranch } from "@/lib/permissions";

import { CustomerForm } from "../../customer-form";

export const metadata: Metadata = { title: "Edit customer" };

export default function EditCustomerPage({ params }: PageProps<"/customers/[id]/edit">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/customers/[id]/edit">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.CUSTOMERS_MANAGE)) return <NoAccess />;
  const { id } = await params;
  const customer = await apiGet<CustomerDetail>(`/customers/${id}`);
  return (
    <>
      <PageHeader title={`Edit ${customer.display_name}`} back={{ href: `/customers/${id}`, label: customer.display_name }} />
      <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
        <CustomerForm customer={customer} />
      </div>
    </>
  );
}
