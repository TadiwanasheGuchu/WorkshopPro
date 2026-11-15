import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { DocumentSequence } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { SequenceRow } from "../settings-forms";

export const metadata: Metadata = { title: "Document numbering" };

export default function NumberingPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={7} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  if (!can(me, P.SETTINGS_VIEW)) return <NoAccess />;
  const sequences = await apiGet<DocumentSequence[]>("/organisation/document-sequences");
  const canManage = can(me, P.SETTINGS_MANAGE);
  return (
    <div className="max-w-3xl">
      <Panel
        title="Document numbering"
        description="Numbers are unique within your organisation. The next number can be raised, never lowered, so printed numbers are never reused."
        flush
      >
        <ul className="divide-y divide-border">
          {sequences.map((s) => (
            <SequenceRow key={s.document_type} sequence={s} canManage={canManage} />
          ))}
        </ul>
      </Panel>
    </div>
  );
}
