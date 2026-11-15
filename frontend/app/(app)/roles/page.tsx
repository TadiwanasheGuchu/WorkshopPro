import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { NoAccess, PageHeader, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Role } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

export const metadata: Metadata = { title: "Roles" };

export default function RolesPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <RolesContent />
    </Suspense>
  );
}

async function RolesContent() {
  const me = await requireMe();
  if (!can(me, P.USERS_VIEW)) return <NoAccess />;
  const roles = await apiGet<Role[]>("/roles");

  return (
    <>
      <PageHeader
        title="Users & roles"
        actions={
          can(me, P.ROLES_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/roles/new">New role</Link>
            </Button>
          ) : null
        }
      />
      <TabNav
        active="/roles"
        tabs={[
          { href: "/users", label: "Users" },
          { href: "/roles", label: "Roles" },
        ]}
      />
      <Panel flush>
        <ul className="divide-y divide-border">
          {roles.map((role) => (
            <li key={role.id}>
              <Link href={`/roles/${role.id}`} className="flex items-start justify-between gap-4 px-4 py-3 hover:bg-mist">
                <div className="min-w-0">
                  <p className="font-medium text-steel">{role.name}</p>
                  <p className="text-sm text-muted">{role.description ?? "No description"}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1 text-sm">
                  {role.is_owner ? <StatusBadge tone="active">Full access</StatusBadge> : null}
                  <span className="text-muted tabular-nums">
                    {role.user_count} {role.user_count === 1 ? "user" : "users"}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
