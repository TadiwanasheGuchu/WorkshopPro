import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Part, PartCategory, TaxRate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { PartForm } from "../../part-form";

export const metadata: Metadata = { title: "Edit part" };

export default function EditPartPage({ params }: PageProps<"/inventory/parts/[id]/edit">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/inventory/parts/[id]/edit">["params"] }) {
  const me = await requireMe();
  if (!can(me, P.INVENTORY_CATALOGUE)) return <NoAccess />;
  const { id } = await params;
  const [part, categories, taxRates] = await Promise.all([
    apiGet<Part>(`/inventory/parts/${id}`),
    apiGet<PartCategory[]>("/inventory/categories"),
    apiGet<TaxRate[]>("/organisation/tax-rates"),
  ]);
  return (
    <>
      <PageHeader title={`Edit ${part.sku}`} back={{ href: `/inventory/parts/${part.id}`, label: part.name }} />
      <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
        <PartForm part={part} categories={categories} taxRates={taxRates} />
      </div>
    </>
  );
}
