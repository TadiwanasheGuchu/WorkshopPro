import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Permission } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { RoleForm } from "../role-form";

export const metadata: Metadata = { title: "New role" };

export default function NewRolePage() {
  return (
    <>
      <PageHeader title="New role" back={{ href: "/roles", label: "Roles" }} />
      <Suspense fallback={<PanelSkeleton rows={8} />}>
        <NewRoleContent />
      </Suspense>
    </>
  );
}

async function NewRoleContent() {
  const me = await requireMe();
  if (!can(me, P.ROLES_MANAGE)) return <NoAccess />;
  const catalogue = await apiGet<Permission[]>("/permissions");
  return (
    <div className="max-w-3xl rounded-panel border border-border bg-surface p-4 sm:p-5">
      <RoleForm catalogue={catalogue} grantable={me.permissions} />
    </div>
  );
}
