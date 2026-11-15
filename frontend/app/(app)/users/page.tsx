import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { describeAssignment, UserStatusBadge } from "@/components/app/user-status";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, User } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { P, can } from "@/lib/permissions";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage({ searchParams }: PageProps<"/users">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <UsersContent searchParams={searchParams} />
    </Suspense>
  );
}

const STATUSES = ["active", "invited", "deactivated"] as const;

async function UsersContent({ searchParams }: { searchParams: PageProps<"/users">["searchParams"] }) {
  const me = await requireMe();
  if (!can(me, P.USERS_VIEW)) return <NoAccess />;

  const params = await searchParams;
  const search = typeof params.search === "string" ? params.search : "";
  const status = STATUSES.find((s) => s === params.status);
  const roleId = typeof params.role_id === "string" && /^[0-9a-f-]{36}$/.test(params.role_id) ? params.role_id : undefined;
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<User>>(
    `/users${query({ search, status, role_id: roleId, page, page_size: 25 })}`,
  );
  const prefs = me.organisation;

  return (
    <>
      <PageHeader
        title="Users & roles"
        actions={
          can(me, P.USERS_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/users/new">Invite user</Link>
            </Button>
          ) : null
        }
      />
      <TabNav
        active="/users"
        tabs={[
          { href: "/users", label: "Users" },
          { href: "/roles", label: "Roles" },
        ]}
      />

      <form method="get" className="mb-4 flex flex-col gap-2 sm:flex-row" role="search">
        {roleId ? <input type="hidden" name="role_id" value={roleId} /> : null}
        <label className="sr-only" htmlFor="user-search">
          Search users
        </label>
        <Input id="user-search" name="search" defaultValue={search} placeholder="Search name or email" className="sm:max-w-xs" />
        <label className="sr-only" htmlFor="user-status">
          Status
        </label>
        <Select id="user-status" name="status" defaultValue={status ?? ""} className="sm:w-44">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="invited">Invited</option>
          <option value="deactivated">Deactivated</option>
        </Select>
        <Button type="submit">Filter</Button>
      </form>

      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={search || status || roleId ? "No users match these filters" : "No users yet"}>
            {search || status || roleId ? (
              <Link href="/users" className="text-steel hover:underline">
                Clear filters
              </Link>
            ) : null}
          </EmptyState>
        ) : (
          <>
            {/* Desktop table */}
            <table className="hidden w-full text-left md:table">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 font-medium">Roles</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Last sign-in</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((user) => (
                  <tr key={user.id} className="hover:bg-mist">
                    <td className="px-4 py-3">
                      <Link href={`/users/${user.id}`} className="font-medium text-steel hover:underline">
                        {user.full_name}
                      </Link>
                      <div className="text-xs text-muted">{user.email}</div>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {user.role_assignments.map(describeAssignment).join(", ") || <span className="text-muted">No roles</span>}
                    </td>
                    <td className="px-4 py-3">
                      <UserStatusBadge status={user.status} />
                    </td>
                    <td className="px-4 py-3 text-sm tabular-nums text-muted">
                      {formatDateTime(user.last_login_at, prefs)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Phone list */}
            <ul className="divide-y divide-border md:hidden">
              {data.items.map((user) => (
                <li key={user.id}>
                  <Link href={`/users/${user.id}`} className="block px-4 py-3 active:bg-mist">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium">{user.full_name}</p>
                        <p className="truncate text-xs text-muted">{user.email}</p>
                      </div>
                      <UserStatusBadge status={user.status} />
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      {user.role_assignments.map(describeAssignment).join(", ") || "No roles"}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="border-t border-border">
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            hrefFor={(p) => `/users${query({ search, status, role_id: roleId, page: p })}`}
          />
        </div>
      </Panel>
    </>
  );
}
