import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Alert } from "@/components/ui/alert";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Permission, Role } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { RoleForm } from "../role-form";

export const metadata: Metadata = { title: "Role" };

export default function RolePage({ params }: PageProps<"/roles/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <RoleContent params={params} />
    </Suspense>
  );
}

async function RoleContent({ params }: { params: PageProps<"/roles/[id]">["params"] }) {
  const me = await requireMe();
  if (!can(me, P.USERS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const [role, catalogue] = await Promise.all([apiGet<Role>(`/roles/${id}`), apiGet<Permission[]>("/permissions")]);
  const editable = can(me, P.ROLES_MANAGE) && !role.is_owner;

  return (
    <>
      <PageHeader
        title={role.name}
        description={role.description ?? undefined}
        back={{ href: "/roles", label: "Roles" }}
      />
      <div className="max-w-3xl space-y-4">
        {role.is_owner ? (
          <Alert tone="info" title="The owner role cannot be changed">
            Owners always have every permission, including permissions added in future updates.
          </Alert>
        ) : null}
        <p className="text-sm text-muted">
          Assigned to{" "}
          <Link href={`/users?role_id=${role.id}`} className="text-steel hover:underline">
            {role.user_count} {role.user_count === 1 ? "user" : "users"}
          </Link>
          .
        </p>
        <Panel>
          {editable ? (
            <RoleForm role={role} catalogue={catalogue} grantable={me.permissions} />
          ) : (
            <ul className="space-y-2">
              {catalogue
                .filter((p) => role.permissions.includes(p.code))
                .map((p) => (
                  <li key={p.code}>
                    <p className="font-medium">{p.label}</p>
                    <p className="text-sm text-muted">{p.description}</p>
                  </li>
                ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
