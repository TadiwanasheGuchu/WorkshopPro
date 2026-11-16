import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { SupplierForm } from "../supplier-form";

export const metadata: Metadata = { title: "Add supplier" };

export default function NewSupplierPage() {
  return (
    <>
      <PageHeader title="Add supplier" back={{ href: "/suppliers", label: "Suppliers" }} />
      <Suspense fallback={<PanelSkeleton rows={6} />}>
        <Content />
      </Suspense>
    </>
  );
}

async function Content() {
  const me = await requireMe();
  if (!can(me, P.SUPPLIERS_MANAGE)) return <NoAccess />;
  return (
    <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
      <SupplierForm />
    </div>
  );
}
