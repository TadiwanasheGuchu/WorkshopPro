import type { Metadata } from "next";
import { Suspense } from "react";

import { Alert } from "@/components/ui/alert";
import { NoAccess, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { InspectionTemplate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { TemplateEditor, toText } from "../template-editor";

export const metadata: Metadata = { title: "Inspection checklist" };

export default function TemplatePage({ params, searchParams }: PageProps<"/settings/inspection-templates/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({
  params,
  searchParams,
}: {
  params: PageProps<"/settings/inspection-templates/[id]">["params"];
  searchParams: PageProps<"/settings/inspection-templates/[id]">["searchParams"];
}) {
  const me = await requireMe();
  const { id } = await params;
  const { saved } = await searchParams;
  const manage = can(me, P.INSPECTION_TEMPLATES_MANAGE);
  if (id === "new") return manage ? <TemplateEditor template={null} /> : <NoAccess />;
  const template = await apiGet<InspectionTemplate>(`/inspection-templates/${id}`);
  return (
    <div className="space-y-4">
      {saved ? <Alert tone="success" className="max-w-3xl">Checklist saved.</Alert> : null}
      {manage ? (
        <TemplateEditor key={template.id + template.item_count} template={template} />
      ) : (
        <pre className="max-w-3xl rounded-panel border border-border bg-surface p-4 font-mono text-sm whitespace-pre-wrap">{toText(template)}</pre>
      )}
    </div>
  );
}
