import type { Metadata } from "next";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { NotificationTemplate } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { TemplateForm } from "./template-form";

export const metadata: Metadata = { title: "Message templates" };

export default function TemplatesPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.NOTIFICATIONS_VIEW)) return <NoAccess />;
  const templates = await apiGet<NotificationTemplate[]>("/notification-templates");
  const canEdit = can(me, P.NOTIFICATIONS_MANAGE);

  return (
    <>
      <PageHeader
        title="Message templates"
        description="WhatsApp is used only for customers who gave WhatsApp consent, and only for events with an approved template. Otherwise the email is sent, unless the customer withdrew email consent."
        back={{ href: "/notifications", label: "Notifications" }}
      />
      <div className="space-y-5">
        {templates.map((t) => (
          <Panel key={t.event} title={t.label} actions={<StatusBadge tone={t.is_enabled ? "success" : "neutral"}>{t.is_enabled ? "On" : "Off"}</StatusBadge>}>
            <TemplateForm template={t} canEdit={canEdit} />
          </Panel>
        ))}
      </div>
    </>
  );
}
