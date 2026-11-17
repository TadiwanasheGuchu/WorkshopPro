import type { Metadata } from "next";

import { StatusBadge, type StatusTone } from "@/components/status-badge";
import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { AppointmentRequest, DateFormat, PortalMe, PortalVehicle, Ref } from "@/lib/api/types";
import { formatDate, formatDateTime } from "@/lib/format";

import { CancelRequestButton, RequestForm } from "./request-form";

export const metadata: Metadata = { title: "Bookings" };

const STATUS: Record<AppointmentRequest["status"], { tone: StatusTone; label: string }> = {
  pending: { tone: "waiting", label: "Waiting for the workshop" },
  confirmed: { tone: "success", label: "Booked" },
  declined: { tone: "danger", label: "Not possible" },
  cancelled: { tone: "neutral", label: "Cancelled" },
};
const TIME = { morning: "morning", afternoon: "afternoon", any: "any time" } as const;

export default async function PortalBookingsPage() {
  const [me, vehicles, branches, requests] = await Promise.all([
    portalGet<PortalMe>("/me"),
    portalGet<PortalVehicle[]>("/vehicles"),
    portalGet<Ref[]>("/branches"),
    portalGet<AppointmentRequest[]>("/appointment-requests"),
  ]);
  const prefs = { timezone: me.timezone, date_format: me.date_format as DateFormat };

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Book a service</h1>
      <Panel title="Request a booking">
        <p className="mb-4 text-sm text-muted">Choose a day that suits you. The workshop confirms the exact time.</p>
        <RequestForm vehicles={vehicles} branches={branches} />
      </Panel>
      {requests.length ? (
        <Panel title="Your requests" flush>
          <ul className="divide-y divide-border">
            {requests.map((r) => {
              const st = STATUS[r.status];
              return (
                <li key={r.id} className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium">{r.service_requested}</p>
                    <p className="text-xs text-muted">
                      {r.vehicle ? `${r.vehicle.name} · ` : ""}
                      {r.appointment_starts_at ? `Booked for ${formatDateTime(r.appointment_starts_at, prefs)}` : `${formatDate(r.preferred_date, prefs)}, ${TIME[r.time_of_day]}`}
                      {` · ${r.branch.name}`}
                    </p>
                    {r.decline_reason ? <p className="mt-1 text-xs">{r.decline_reason}</p> : null}
                  </div>
                  <span className="flex items-center gap-2">
                    <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                    {r.status === "pending" ? <CancelRequestButton id={r.id} /> : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
