import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { PartCategory, TaxRate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { PartForm } from "../part-form";

export const metadata: Metadata = { title: "Add part" };

export default function NewPartPage() {
  return (
    <>
      <PageHeader title="Add part" back={{ href: "/inventory/parts", label: "Parts catalogue" }} />
      <Suspense fallback={<PanelSkeleton rows={8} />}>
        <Content />
      </Suspense>
    </>
  );
}

async function Content() {
  const me = await requireMe();
  if (!can(me, P.INVENTORY_CATALOGUE)) return <NoAccess />;
  const [categories, taxRates] = await Promise.all([apiGet<PartCategory[]>("/inventory/categories"), apiGet<TaxRate[]>("/organisation/tax-rates")]);
  return (
    <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
      <PartForm categories={categories} taxRates={taxRates} />
    </div>
  );
}
