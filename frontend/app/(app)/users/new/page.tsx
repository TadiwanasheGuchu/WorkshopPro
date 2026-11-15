import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Branch, Page, Role } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { InviteForm } from "./invite-form";

export const metadata: Metadata = { title: "Invite user" };

export default function InviteUserPage() {
  return (
    <>
      <PageHeader
        title="Invite user"
        description="They receive an email with a link to set their password. The link expires after 7 days."
        back={{ href: "/users", label: "Users" }}
      />
      <Suspense fallback={<PanelSkeleton rows={5} />}>
        <InviteContent />
      </Suspense>
    </>
  );
}

async function InviteContent() {
  const me = await requireMe();
  if (!can(me, P.USERS_MANAGE)) return <NoAccess />;
  const [roles, branches] = await Promise.all([
    apiGet<Role[]>("/roles"),
    apiGet<Page<Branch>>("/branches?page_size=100"),
  ]);
  const assignable = roles.filter((r) => !r.is_owner || me.is_owner);
  return (
    <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
      <InviteForm roles={assignable} branches={branches.items} />
    </div>
  );
}
