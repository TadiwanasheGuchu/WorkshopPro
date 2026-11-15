import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { NoAccess, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { InspectionTemplate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Inspection checklists" };

export default function TemplatesPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={4} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  const manage = can(me, P.INSPECTION_TEMPLATES_MANAGE);
  if (!manage && !canInAnyBranch(me, P.INSPECTIONS_PERFORM)) return <NoAccess />;
  const templates = await apiGet<InspectionTemplate[]>("/inspection-templates");
  return (
    <div className="max-w-3xl">
      <Panel
        title="Inspection checklists"
        description="Used for intake and quality inspections."
        flush
        actions={
          manage ? (
            <Button asChild size="sm" variant="primary">
              <Link href="/settings/inspection-templates/new">New checklist</Link>
            </Button>
          ) : null
        }
      >
        <ul className="divide-y divide-border">
          {templates.map((t) => (
            <li key={t.id}>
              <Link href={`/settings/inspection-templates/${t.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
                <div>
                  <p className="font-medium text-steel">{t.name}</p>
                  {t.description ? <p className="text-xs text-muted">{t.description}</p> : null}
                </div>
                <span className="flex items-center gap-2 text-sm text-muted">
                  {t.is_default ? <StatusBadge tone="active">Default</StatusBadge> : null}
                  <span className="tabular-nums">{t.item_count} items</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
