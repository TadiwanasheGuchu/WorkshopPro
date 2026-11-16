import type { Metadata } from "next";
import { Suspense } from "react";

import { NoAccess, PageHeader, PanelSkeleton } from "@/components/ui/page";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

import { BookingForm } from "./booking-form";

export const metadata: Metadata = { title: "Book appointment" };

export default function NewAppointmentPage({ searchParams }: PageProps<"/appointments/new">) {
  return (
    <>
      <PageHeader title="Book appointment" description="Times are in the workshop's local time." back={{ href: "/appointments", label: "Appointments" }} />
      <Suspense fallback={<PanelSkeleton rows={6} />}>
        <Content searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/appointments/new">["searchParams"] }) {
  const me = await requireMe();
  const branches = me.branches.filter((b) => can(me, P.APPOINTMENTS_MANAGE, b.id));
  if (!branches.length) return <NoAccess />;
  const params = await searchParams;
  const branch = branches.find((b) => b.id === params.branch)?.id ?? branches[0].id;
  const date =
    typeof params.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(params.date)
      ? params.date
      : new Intl.DateTimeFormat("en-CA", { timeZone: me.organisation.timezone }).format(new Date());
  return (
    <div className="rounded-panel border border-border bg-surface p-4 sm:p-5">
      <BookingForm branches={branches} initialBranch={branch} initialDate={date} />
    </div>
  );
}
