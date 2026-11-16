import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Supplier } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { SupplierForm } from "../../supplier-form";

export const metadata: Metadata = { title: "Edit supplier" };

export default function EditSupplierPage({ params }: PageProps<"/suppliers/[id]/edit">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/suppliers/[id]/edit">["params"] }) {
  const me = await requireMe();
  if (!can(me, P.SUPPLIERS_MANAGE)) return <NoAccess />;
  const { id } = await params;
  const supplier = await apiGet<Supplier>(`/suppliers/${id}`);
  return (
    <>
      <PageHeader title={`Edit ${supplier.name}`} back={{ href: `/suppliers/${supplier.id}`, label: supplier.name }} />
      <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
        <SupplierForm supplier={supplier} />
      </div>
    </>
  );
}
