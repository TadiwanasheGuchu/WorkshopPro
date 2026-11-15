import { CircleCheck, Circle } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { Me, Page, ServiceBay, TaxRate, User } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" />
      <Suspense fallback={<PanelSkeleton rows={5} />}>
        <DashboardContent />
      </Suspense>
    </>
  );
}

async function DashboardContent() {
  const me = await requireMe();
  const isAdmin = can(me, P.SETTINGS_MANAGE) || can(me, P.USERS_MANAGE);
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-5">
        {isAdmin ? <SetupChecklist me={me} /> : null}
        <Panel title="Workshop operations">
          <p className="text-muted">
            Job cards, inspections, customers and vehicles are the next module to be delivered. This
            dashboard will then show jobs received today, jobs awaiting approval or parts, and vehicles
            ready for collection.
          </p>
        </Panel>
      </div>
      <Panel title="Your access" className="self-start">
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-xs text-muted">Organisation</dt>
            <dd>{me.organisation.name}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Branches</dt>
            <dd>{me.branches.map((b) => b.name).join(", ") || "None assigned"}</dd>
          </div>
          {me.is_owner ? (
            <div>
              <dt className="text-xs text-muted">Role</dt>
              <dd>
                <StatusBadge tone="active">Owner</StatusBadge>
              </dd>
            </div>
          ) : null}
        </dl>
      </Panel>
    </div>
  );
}

async function SetupChecklist({ me }: { me: Me }) {
  const [taxRates, users, bays] = await Promise.all([
    can(me, P.SETTINGS_VIEW) ? apiGet<TaxRate[]>("/organisation/tax-rates") : Promise.resolve(null),
    can(me, P.USERS_VIEW) ? apiGet<Page<User>>("/users?page_size=1") : Promise.resolve(null),
    me.branches[0] ? apiGet<ServiceBay[]>(`/branches/${me.branches[0].id}/service-bays`) : Promise.resolve(null),
  ]);

  const steps = [
    {
      done: (bays?.length ?? 0) > 0,
      label: "Add service bays to your branch",
      href: me.branches[0] ? `/branches/${me.branches[0].id}` : "/branches",
      show: bays !== null,
    },
    {
      done: (users?.total ?? 0) > 1,
      label: "Invite your staff",
      href: "/users/new",
      show: users !== null && can(me, P.USERS_MANAGE),
    },
    {
      done: (taxRates?.length ?? 0) > 0,
      label: "Configure tax rates (confirm with your tax adviser)",
      href: "/settings/tax-rates",
      show: taxRates !== null && can(me, P.SETTINGS_MANAGE),
    },
    {
      done: false,
      label: "Review document numbering for job cards, quotations and invoices",
      href: "/settings/numbering",
      show: can(me, P.SETTINGS_MANAGE),
      optional: true,
    },
  ].filter((s) => s.show);

  if (steps.every((s) => s.done || s.optional)) return null;

  return (
    <Panel title="Set up your workshop" flush>
      <ul className="divide-y divide-border">
        {steps.map((step) => (
          <li key={step.label}>
            <Link href={step.href} className="flex items-center gap-3 px-4 py-3 hover:bg-mist">
              {step.done ? (
                <CircleCheck className="size-5 text-status-success" aria-label="Done" />
              ) : (
                <Circle className="size-5 text-muted" aria-label="To do" />
              )}
              <span className={step.done ? "text-muted line-through" : undefined}>{step.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
