import type { Metadata } from "next";
import { Suspense } from "react";

import { AuditList } from "@/components/app/audit-list";
import { describeAssignment, UserStatusBadge } from "@/components/app/user-status";
import { Alert } from "@/components/ui/alert";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { AuditLogEntry, Branch, Page, Role, User } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { P, can } from "@/lib/permissions";

import { ProfileForm, RolesForm, StatusActions } from "./user-actions";

export const metadata: Metadata = { title: "User" };

export default function UserPage({ params, searchParams }: PageProps<"/users/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <UserContent params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function UserContent({
  params,
  searchParams,
}: {
  params: PageProps<"/users/[id]">["params"];
  searchParams: PageProps<"/users/[id]">["searchParams"];
}) {
  const me = await requireMe();
  if (!can(me, P.USERS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const { invited } = await searchParams;

  const user = await apiGet<User>(`/users/${id}`);
  // Owners' accounts can only be changed by owners (enforced by the API).
  const canManage = can(me, P.USERS_MANAGE) && (!user.is_owner || me.is_owner);
  const [roles, branches, activity] = await Promise.all([
    canManage ? apiGet<Role[]>("/roles") : Promise.resolve([]),
    canManage ? apiGet<Page<Branch>>("/branches?page_size=100") : Promise.resolve(null),
    can(me, P.AUDIT_VIEW)
      ? apiGet<Page<AuditLogEntry>>(`/audit-logs?entity_type=user&entity_id=${id}&page_size=10`)
      : Promise.resolve(null),
  ]);
  const prefs = me.organisation;

  return (
    <>
      <PageHeader
        title={user.full_name}
        description={user.email}
        back={{ href: "/users", label: "Users" }}
        actions={<UserStatusBadge status={user.status} />}
      />
      {invited ? (
        <Alert tone="success" className="mb-5">
          Invitation sent to {user.email}.
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <Panel title="Details">
            {canManage ? (
              <ProfileForm user={user} />
            ) : (
              <DetailList
                items={[
                  { label: "Name", value: user.full_name },
                  { label: "Email", value: user.email },
                  { label: "Phone", value: user.phone },
                ]}
              />
            )}
          </Panel>

          <Panel title="Roles" description="What this user can do, and in which branches.">
            {canManage && branches ? (
              <RolesForm
                user={user}
                roles={roles.filter((r) => !r.is_owner || me.is_owner)}
                branches={branches.items}
              />
            ) : (
              <ul className="space-y-1 text-sm">
                {user.role_assignments.map((a) => (
                  <li key={a.id}>{describeAssignment(a)}</li>
                ))}
              </ul>
            )}
          </Panel>

          {canManage ? (
            <Panel title="Account status">
              <StatusActions user={user} isSelf={user.id === me.id} />
            </Panel>
          ) : null}
        </div>

        <div className="space-y-5">
          <Panel title="Account">
            <DetailList
              items={[
                { label: "Invited", value: formatDateTime(user.invited_at, prefs) },
                { label: "Activated", value: formatDateTime(user.activated_at, prefs) },
                { label: "Last sign-in", value: formatDateTime(user.last_login_at, prefs) },
              ]}
            />
          </Panel>
          {activity ? (
            <Panel title="Recent activity" flush>
              <AuditList entries={activity.items} me={me} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
