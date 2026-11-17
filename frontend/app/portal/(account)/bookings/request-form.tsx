"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { PortalVehicle, Ref } from "@/lib/api/types";

export function RequestForm({ vehicles, branches }: { vehicles: PortalVehicle[]; branches: Ref[] }) {
  const router = useRouter();
  const [vehicle, setVehicle] = useState(vehicles[0]?.id ?? "");
  const [branch, setBranch] = useState(branches[0]?.id ?? "");
  const [date, setDate] = useState("");
  const [time, setTime] = useState<"morning" | "afternoon" | "any">("morning");
  const [service, setService] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const valid = Boolean(branch && date && service.trim().length >= 3);

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        setDone(false);
        try {
          await api("POST", "/portal/appointment-requests", {
            branch_id: branch,
            vehicle_id: vehicle || null,
            preferred_date: date,
            time_of_day: time,
            service_requested: service.trim(),
            notes: notes.trim() || null,
          });
          setDone(true);
          setService("");
          setNotes("");
          router.refresh();
        } catch (err) {
          setError(errorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {done ? <Alert tone="success">Request sent. The workshop will confirm the time.</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {vehicles.length ? (
          <Field label="Vehicle">
            {(p) => (
              <Select {...p} value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
                <option value="">Another vehicle</option>
              </Select>
            )}
          </Field>
        ) : null}
        {branches.length > 1 ? (
          <Field label="Branch" required>
            {(p) => (
              <Select {...p} value={branch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ) : null}
        <Field label="Preferred day" required>
          {(p) => <Input {...p} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field label="Time of day">
          {(p) => (
            <Select {...p} value={time} onChange={(e) => setTime(e.target.value as typeof time)}>
              <option value="morning">Morning</option>
              <option value="afternoon">Afternoon</option>
              <option value="any">Any time</option>
            </Select>
          )}
        </Field>
      </div>
      <Field label="What do you need?" required hint="For example: annual service, brakes squeal, aircon not cold.">
        {(p) => <Input {...p} maxLength={500} value={service} onChange={(e) => setService(e.target.value)} />}
      </Field>
      <Field label="Anything else we should know">{(p) => <Textarea {...p} rows={2} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
        Request booking
      </Button>
    </form>
  );
}

export function CancelRequestButton({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      variant="ghost"
      loading={busy}
      onClick={async () => {
        setBusy(true);
        await api("POST", `/portal/appointment-requests/${id}/cancel`).catch(() => undefined);
        setBusy(false);
        router.refresh();
      }}
    >
      Cancel
    </Button>
  );
}
