"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { Panel } from "@/components/ui/page";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { AppointmentRequest, Ref } from "@/lib/api/types";

const TIME_LABEL = { morning: "Morning", afternoon: "Afternoon", any: "Any time" } as const;

function ConfirmButton({ request, bays }: { request: AppointmentRequest; bays: Ref[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(request.preferred_date);
  const [time, setTime] = useState(request.time_of_day === "afternoon" ? "13:00" : "08:00");
  const [duration, setDuration] = useState("60");
  const [bay, setBay] = useState("");
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Confirm
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Book ${request.customer.name}`} description={request.service_requested}>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("POST", `/appointment-requests/${request.id}/confirm`, {
                date,
                start_time: time,
                duration_minutes: Number(duration),
                service_bay_id: bay || null,
                notify_customer: notify,
              });
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Date" required>
              {(p) => <Input {...p} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
            </Field>
            <Field label="Start" required>
              {(p) => <Input {...p} type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} />}
            </Field>
            <Field label="Duration">
              {(p) => (
                <Select {...p} value={duration} onChange={(e) => setDuration(e.target.value)}>
                  {[30, 60, 90, 120, 180, 240, 480].map((m) => (
                    <option key={m} value={m}>
                      {m < 60 ? `${m} min` : `${m / 60} h`}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          {bays.length ? (
            <Field label="Service bay">
              {(p) => (
                <Select {...p} value={bay} onChange={(e) => setBay(e.target.value)}>
                  <option value="">Not assigned</option>
                  {bays.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          ) : null}
          <Checkbox label="Let the customer know" description="By WhatsApp or email, following their consent." checked={notify} onChange={(e) => setNotify(e.target.checked)} />
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy}>
              Book appointment
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

function DeclineButton({ request }: { request: AppointmentRequest }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Decline
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title="Decline request" description="The customer sees the reason in the portal.">
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("POST", `/appointment-requests/${request.id}/decline`, { reason: reason.trim() });
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="danger" loading={busy} disabled={reason.trim().length < 3}>
              Decline
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function BookingRequests({ requests, bays, canManage, formatDay }: { requests: AppointmentRequest[]; bays: Ref[]; canManage: boolean; formatDay: Record<string, string> }) {
  if (!requests.length) return null;
  return (
    <Panel title={`Booking requests (${requests.length})`} flush className="mb-5">
      <ul className="divide-y divide-border">
        {requests.map((r) => (
          <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
            <div className="min-w-0 text-sm">
              <p className="font-medium">
                {r.customer.name}
                {r.vehicle ? <span className="font-normal text-muted"> · {r.vehicle.name}</span> : null}
              </p>
              <p>
                {formatDay[r.preferred_date] ?? r.preferred_date}, {TIME_LABEL[r.time_of_day].toLowerCase()} · {r.service_requested}
              </p>
              {r.notes ? <p className="text-xs text-muted">{r.notes}</p> : null}
            </div>
            {canManage ? (
              <span className="flex gap-2">
                <ConfirmButton request={r} bays={bays} />
                <DeclineButton request={r} />
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
