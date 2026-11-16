import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Appointment, DaySchedule, Ref } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { shortTime } from "@/lib/format";
import { P, can } from "@/lib/permissions";

import { AppointmentCard } from "./appointment-card";

export const metadata: Metadata = { title: "Appointments" };

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function todayIn(timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

function shift(day: string, days: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function heading(day: string): string {
  return new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${day}T12:00:00Z`),
  );
}

export default function AppointmentsPage({ searchParams }: PageProps<"/appointments">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={6} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/appointments">["searchParams"] }) {
  const me = await requireMe();
  const branches = me.branches.filter((b) => can(me, P.APPOINTMENTS_VIEW, b.id));
  if (!branches.length) return <NoAccess />;
  const params = await searchParams;
  const branch = branches.find((b) => b.id === params.branch) ?? branches[0];
  const today = todayIn(me.organisation.timezone);
  const day = typeof params.date === "string" && DATE_RE.test(params.date) ? params.date : today;
  const schedule = await apiGet<DaySchedule>(`/appointments/day${query({ branch_id: branch.id, date: day })}`);
  const canManage = can(me, P.APPOINTMENTS_MANAGE, branch.id);
  const canCheckIn = canManage && can(me, P.JOB_CARDS_CREATE, branch.id);
  const href = (d: string) => `/appointments${query({ branch: branches.length > 1 ? branch.id : undefined, date: d === today ? undefined : d })}`;

  const columns: { bay: Ref | null; items: Appointment[] }[] = [
    ...schedule.bays.map((bay) => ({ bay, items: schedule.appointments.filter((a) => a.service_bay?.id === bay.id) })),
    { bay: null, items: schedule.appointments.filter((a) => !a.service_bay) },
  ].filter((c) => c.bay !== null || c.items.length > 0);

  return (
    <>
      <PageHeader
        title="Appointments"
        actions={
          canManage ? (
            <Button asChild variant="primary">
              <Link href={`/appointments/new${query({ branch: branch.id, date: day })}`}>Book appointment</Link>
            </Button>
          ) : null
        }
      />
      <form method="get" className="mb-4 flex flex-wrap items-end gap-2">
        {branches.length > 1 ? (
          <label className="text-sm">
            <span className="mb-1 block font-medium">Branch</span>
            <Select name="branch" defaultValue={branch.id}>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </label>
        ) : null}
        <label className="text-sm">
          <span className="mb-1 block font-medium">Date</span>
          <Input type="date" name="date" defaultValue={day} />
        </label>
        <Button type="submit">Show</Button>
        <div className="ml-auto flex gap-1">
          <Button asChild size="sm">
            <Link href={href(shift(day, -1))}>Previous day</Link>
          </Button>
          {day !== today ? (
            <Button asChild size="sm">
              <Link href={href(today)}>Today</Link>
            </Button>
          ) : null}
          <Button asChild size="sm">
            <Link href={href(shift(day, 1))}>Next day</Link>
          </Button>
        </div>
      </form>

      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">{heading(day)}</h2>
        <p className="text-sm text-muted">
          {schedule.is_closed
            ? `${branch.name} is closed on this day`
            : schedule.opens_at
              ? `${branch.name} open ${shortTime(schedule.opens_at)}–${shortTime(schedule.closes_at)}`
              : branch.name}
          {" · "}
          {schedule.appointments.filter((a) => a.status === "booked").length} booked
        </p>
      </div>

      {schedule.appointments.length === 0 ? (
        <div className="rounded-panel border border-border bg-surface">
          <EmptyState title="No appointments on this day" />
        </div>
      ) : (
        <>
          {/* Phones: one list in time order. */}
          <div className="space-y-2 md:hidden">
            {schedule.appointments.map((a) => (
              <AppointmentCard key={a.id} appt={a} canManage={canManage} canCheckIn={canCheckIn} />
            ))}
          </div>
          {/* Tablets and desktops: a column per service bay. */}
          <div className="hidden gap-3 overflow-x-auto pb-2 md:flex">
            {columns.map((c) => (
              <section key={c.bay?.id ?? "none"} className="w-64 shrink-0 rounded-panel border border-border bg-mist">
                <h3 className="border-b border-border px-3 py-2 text-sm font-semibold">{c.bay?.name ?? "No bay allocated"}</h3>
                <div className="space-y-2 p-2">
                  {c.items.length ? (
                    c.items.map((a) => <AppointmentCard key={a.id} appt={a} canManage={canManage} canCheckIn={canCheckIn} />)
                  ) : (
                    <p className="px-1 py-2 text-xs text-muted">Free</p>
                  )}
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
