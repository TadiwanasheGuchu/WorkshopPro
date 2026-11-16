"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CustomerPicker, type PickedCustomer } from "@/components/app/customer-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { BranchSummary, Page, Ref, ServiceBay, Vehicle } from "@/lib/api/types";
import { vehicleTitle } from "@/lib/labels";

const DURATIONS = [30, 45, 60, 90, 120, 180, 240, 480];

export function BookingForm({ branches, initialBranch, initialDate }: { branches: BranchSummary[]; initialBranch: string; initialDate: string }) {
  const router = useRouter();
  const [branchId, setBranchId] = useState(initialBranch);
  const [customer, setCustomer] = useState<PickedCustomer | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [date, setDate] = useState(initialDate);
  const [start, setStart] = useState("08:00");
  const [duration, setDuration] = useState(60);
  const [bays, setBays] = useState<ServiceBay[]>([]);
  const [bayId, setBayId] = useState("");
  const [mechanics, setMechanics] = useState<Ref[]>([]);
  const [mechanicId, setMechanicId] = useState("");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<ServiceBay[]>("GET", `/branches/${branchId}/service-bays`),
      api<Ref[]>("GET", `/appointments/bookable-users?branch_id=${branchId}`),
    ])
      .then(([b, m]) => {
        if (cancelled) return;
        setBays(b.filter((x) => x.is_active));
        setMechanics(m);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [branchId]);

  useEffect(() => {
    if (!customer) return;
    let cancelled = false;
    api<Page<Vehicle>>("GET", `/vehicles?customer_id=${customer.id}&page_size=50`)
      .then((p) => {
        if (cancelled) return;
        setVehicles(p.items);
        setVehicleId(p.items.length === 1 ? p.items[0].id : "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [customer]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api("POST", "/appointments", {
        branch_id: branchId,
        customer_id: customer?.id,
        vehicle_id: vehicleId || null,
        date,
        start_time: start,
        duration_minutes: duration,
        service_bay_id: bayId || null,
        assigned_user_id: mechanicId || null,
        reason: reason.trim(),
        notes: notes.trim() || null,
      });
      router.push(`/appointments?branch=${branchId}&date=${date}`);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-5">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {branches.length > 1 ? (
        <Field label="Branch">
          {(p) => (
            <Select {...p} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : null}
      <Field label="Customer" required>
        {(p) => <CustomerPicker inputId={p.id} value={customer} onChange={setCustomer} />}
      </Field>
      {customer ? (
        <Field label="Vehicle" hint="Needed to check the customer in.">
          {(p) => (
            <Select {...p} value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
              <option value="">Not specified</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {vehicleTitle(v)} · {v.make} {v.model}
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Date" required>
          {(p) => <Input {...p} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field label="Start" required>
          {(p) => <Input {...p} type="time" step={300} value={start} onChange={(e) => setStart(e.target.value)} />}
        </Field>
        <Field label="Duration">
          {(p) => (
            <Select {...p} value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
              {DURATIONS.map((d) => (
                <option key={d} value={d}>
                  {d < 60 ? `${d} min` : `${d / 60} h`}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Service bay">
          {(p) => (
            <Select {...p} value={bayId} onChange={(e) => setBayId(e.target.value)}>
              <option value="">Allocate later</option>
              {bays.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Mechanic">
          {(p) => (
            <Select {...p} value={mechanicId} onChange={(e) => setMechanicId(e.target.value)}>
              <option value="">Allocate later</option>
              {mechanics.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Field label="Reason for visit" required>
        {(p) => <Input {...p} value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} placeholder="e.g. 60 000 km service" />}
      </Field>
      <Field label="Notes">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />}</Field>
      <div className="flex gap-2">
        <Button variant="primary" loading={busy} disabled={!customer || !reason.trim() || !date || !start} onClick={() => void submit()}>
          Book appointment
        </Button>
        <Button onClick={() => router.back()}>Cancel</Button>
      </div>
    </div>
  );
}
