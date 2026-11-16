"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusBadge, type StatusTone } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { Appointment, AppointmentStatus, JobCardDetail } from "@/lib/api/types";
import { shortTime } from "@/lib/format";
import { vehicleTitle } from "@/lib/labels";

const STATUS: Record<AppointmentStatus, { tone: StatusTone; label: string }> = {
  booked: { tone: "active", label: "Booked" },
  arrived: { tone: "success", label: "Arrived" },
  cancelled: { tone: "neutral", label: "Cancelled" },
  no_show: { tone: "danger", label: "No-show" },
};

export function AppointmentCard({ appt, canManage, canCheckIn }: { appt: Appointment; canManage: boolean; canCheckIn: boolean }) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"checkin" | "cancel" | null>(null);
  const [odometer, setOdometer] = useState("");
  const [needsReason, setNeedsReason] = useState(false);
  const [odoReason, setOdoReason] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = appt.status === "booked";

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      if (e instanceof ApiError && e.code === "odometer_decrease") setNeedsReason(true);
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`rounded-control border border-border bg-surface p-3 ${open ? "" : "opacity-70"}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-sm font-medium tabular-nums">
          {shortTime(appt.local_start)}–{shortTime(appt.local_end)}
        </p>
        <StatusBadge tone={STATUS[appt.status].tone}>{STATUS[appt.status].label}</StatusBadge>
      </div>
      <p className="mt-1 font-medium">
        <Link href={`/customers/${appt.customer.id}`} className="hover:underline">
          {appt.customer.name}
        </Link>
      </p>
      {appt.vehicle ? (
        <p className="text-sm">
          <span className="font-mono">{vehicleTitle(appt.vehicle)}</span>
          <span className="text-muted">
            {" "}
            · {appt.vehicle.make} {appt.vehicle.model}
          </span>
        </p>
      ) : (
        <p className="text-sm text-muted">Vehicle not specified</p>
      )}
      <p className="mt-1 text-sm">{appt.reason}</p>
      <p className="mt-1 text-xs text-muted">
        {[appt.service_bay?.name, appt.assigned_user?.name].filter(Boolean).join(" · ") || "No bay or mechanic"}
      </p>
      {appt.job_card ? (
        <Link href={`/job-cards/${appt.job_card.id}`} className="mt-1 inline-block font-mono text-sm text-steel hover:underline">
          {appt.job_card.name}
        </Link>
      ) : null}
      {appt.cancellation_reason ? <p className="mt-1 text-xs text-muted">{appt.cancellation_reason}</p> : null}

      {open && canManage ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {canCheckIn ? (
            <Button size="sm" variant="primary" onClick={() => setDialog("checkin")}>
              Check in
            </Button>
          ) : null}
          <Button size="sm" onClick={() => setDialog("cancel")}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={busy && dialog === null}
            onClick={() =>
              void run(async () => {
                await api("POST", `/appointments/${appt.id}/no-show`);
                router.refresh();
              })
            }
          >
            No-show
          </Button>
        </div>
      ) : null}

      <Dialog open={dialog === "checkin"} onOpenChange={(o) => !o && setDialog(null)} title="Check in" description="Opens a job card for this booking.">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Odometer at intake (km)">
            {(p) => <Input {...p} inputMode="numeric" value={odometer} onChange={(e) => setOdometer(e.target.value)} />}
          </Field>
          {needsReason ? (
            <Field label="Reason for lower reading" required>
              {(p) => <Input {...p} value={odoReason} onChange={(e) => setOdoReason(e.target.value)} />}
            </Field>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={Boolean(odometer) && !/^\d{1,7}$/.test(odometer.replace(/\s/g, ""))}
              onClick={() =>
                void run(async () => {
                  const job = await api<JobCardDetail>("POST", `/appointments/${appt.id}/check-in`, {
                    intake_odometer_km: odometer ? Number(odometer.replace(/\s/g, "")) : null,
                    odometer_correction_reason: needsReason ? odoReason.trim() || null : null,
                  });
                  router.push(`/job-cards/${job.id}`);
                })
              }
            >
              Open job card
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={dialog === "cancel"} onOpenChange={(o) => !o && setDialog(null)} title="Cancel appointment">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDialog(null)}>Back</Button>
            <Button
              variant="danger"
              loading={busy}
              disabled={reason.trim().length < 3}
              onClick={() =>
                void run(async () => {
                  await api("POST", `/appointments/${appt.id}/cancel`, { reason: reason.trim() });
                  setDialog(null);
                  router.refresh();
                })
              }
            >
              Cancel appointment
            </Button>
          </div>
        </div>
      </Dialog>
    </article>
  );
}
