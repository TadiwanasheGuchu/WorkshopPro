import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { requireMe } from "@/lib/auth";
import { P, canInAnyBranch } from "@/lib/permissions";

import { CustomerForm } from "../customer-form";

export const metadata: Metadata = { title: "Register customer" };

export default function NewCustomerPage() {
  return (
    <>
      <PageHeader title="Register customer" back={{ href: "/customers", label: "Customers" }} />
      <Suspense fallback={<PanelSkeleton rows={6} />}>
        <Content />
      </Suspense>
    </>
  );
}

async function Content() {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.CUSTOMERS_MANAGE)) return <NoAccess />;
  return (
    <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
      <CustomerForm />
    </div>
  );
}
