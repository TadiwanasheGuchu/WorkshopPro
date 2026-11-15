import { CircleCheck, Circle } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { JobSummaryCounts, Me, Page, ServiceBay, TaxRate, User } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { P, can, canInAnyBranch } from "@/lib/permissions";

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
    <div className="space-y-5">
    <WorkshopStrip me={me} />
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-5">
        {isAdmin ? <SetupChecklist me={me} /> : null}
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

async function WorkshopStrip({ me }: { me: Me }) {
  if (!canInAnyBranch(me, P.JOB_CARDS_VIEW) && !canInAnyBranch(me, P.JOB_CARDS_WORK)) return null;
  const c = await apiGet<JobSummaryCounts>("/job-cards/summary");
  const viewAll = canInAnyBranch(me, P.JOB_CARDS_VIEW);
  const items: { label: string; value: number; href: string; tone?: "danger" | "waiting" | "success" }[] = viewAll
    ? [
        { label: "Received today", value: c.received_today, href: "/job-cards?view=all" },
        { label: "Open jobs", value: c.open_total, href: "/job-cards" },
        { label: "Overdue", value: c.overdue, href: "/job-cards?view=overdue", tone: "danger" },
        { label: "Awaiting approval", value: c.by_status.awaiting_approval, href: "/job-cards?status=awaiting_approval", tone: "waiting" },
        { label: "Awaiting parts", value: c.by_status.awaiting_parts, href: "/job-cards?status=awaiting_parts", tone: "waiting" },
        { label: "Ready for collection", value: c.by_status.ready_for_collection, href: "/job-cards?status=ready_for_collection", tone: "success" },
      ]
    : [
        { label: "My open jobs", value: c.my_assigned_open, href: "/job-cards?view=mine" },
        { label: "Overdue", value: c.overdue, href: "/job-cards?view=overdue", tone: "danger" },
      ];
  const dot = { danger: "bg-status-danger", waiting: "bg-status-waiting", success: "bg-status-success" };
  return (
    <section aria-label="Workshop status" className="rounded-panel border border-border bg-surface">
      <ul className="-mb-px -mr-px grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 [&>li]:border-b [&>li]:border-r [&>li]:border-border">
        {items.map((i) => (
          <li key={i.label}>
            <Link href={i.href} className="block px-4 py-3 hover:bg-mist">
              <span className="flex items-center gap-1.5 text-xs text-muted">
                {i.tone && i.value > 0 ? <span aria-hidden className={`size-1.5 rounded-full ${dot[i.tone]}`} /> : null}
                {i.label}
              </span>
              <span className="mt-0.5 block text-xl font-semibold tabular-nums">{i.value}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
