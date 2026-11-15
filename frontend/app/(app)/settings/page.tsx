import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Organisation, OrganisationSettings } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { OrganisationForm, PreferencesForm } from "./settings-forms";

export const metadata: Metadata = { title: "Settings" };

export default function OrganisationSettingsPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  if (!can(me, P.SETTINGS_VIEW)) return <NoAccess />;
  const [organisation, settings] = await Promise.all([
    apiGet<Organisation>("/organisation"),
    apiGet<OrganisationSettings>("/organisation/settings"),
  ]);
  const readOnly = !can(me, P.SETTINGS_MANAGE);
  return (
    <div className="max-w-4xl space-y-5">
      <Panel title="Organisation" description="Shown on quotations, invoices and customer messages.">
        <OrganisationForm organisation={organisation} readOnly={readOnly} />
      </Panel>
      <Panel title="Preferences">
        <PreferencesForm settings={settings} readOnly={readOnly} />
      </Panel>
    </div>
  );
}
