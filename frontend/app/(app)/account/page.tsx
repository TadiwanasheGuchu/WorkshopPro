import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailList, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { requireMe } from "@/lib/auth";

import { ChangePasswordForm } from "./change-password-form";

export const metadata: Metadata = { title: "Account" };

export default function AccountPage() {
  return (
    <>
      <PageHeader title="Account" />
      <Suspense fallback={<PanelSkeleton rows={4} />}>
        <Content />
      </Suspense>
    </>
  );
}

async function Content() {
  const me = await requireMe();
  return (
    <div className="max-w-2xl space-y-5">
      <Panel title="Your details" description="Ask an administrator to change your name or email.">
        <DetailList
          items={[
            { label: "Name", value: me.full_name },
            { label: "Email", value: me.email },
            { label: "Organisation", value: me.organisation.name },
          ]}
        />
      </Panel>
      <Panel title="Change password" description="You stay signed in here; other devices are signed out.">
        <ChangePasswordForm email={me.email} />
      </Panel>
    </div>
  );
}
