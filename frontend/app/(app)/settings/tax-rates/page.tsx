import type { Metadata } from "next";
import { Suspense } from "react";

import { Alert } from "@/components/ui/alert";
import { EmptyState, NoAccess, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { TaxRate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { AddTaxRateButton } from "./add-tax-rate";
import { TaxRateRow } from "../settings-forms";

export const metadata: Metadata = { title: "Tax rates" };

export default function TaxRatesPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={4} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  if (!can(me, P.SETTINGS_VIEW)) return <NoAccess />;
  const rates = await apiGet<TaxRate[]>("/organisation/tax-rates");
  const canManage = can(me, P.SETTINGS_MANAGE);
  return (
    <div className="max-w-3xl space-y-4">
      <Alert tone="info" title="WorkshopPro does not assume any tax rate">
        Enter the rates that apply to your business and confirm them with a qualified Namibian
        accountant or tax adviser. Changes apply to new documents only.
      </Alert>
      <Panel title="Tax rates" flush actions={canManage ? <AddTaxRateButton /> : null}>
        {rates.length === 0 ? (
          <EmptyState title="No tax rates configured">
            Quotations and invoices need at least one rate once those modules are in use.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {rates.map((r) => (
              <TaxRateRow key={r.id} rate={r} canManage={canManage} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
