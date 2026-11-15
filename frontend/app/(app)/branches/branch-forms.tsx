"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { BranchDetail, OperatingHours, ServiceBay } from "@/lib/api/types";
import { WEEKDAYS, shortTime } from "@/lib/format";
import { applyApiError, nullIfBlank } from "@/lib/forms";

const branchSchema = z.object({
  name: z.string().trim().min(1, "Enter a branch name.").max(200),
  code: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z0-9-]{1,12}$/, "1–12 letters, digits or hyphens."),
  phone: z.string().max(50),
  email: z.union([z.literal(""), z.email("Enter a valid email address.")]),
  address_line1: z.string().max(200),
  address_line2: z.string().max(200),
  city: z.string().max(100),
  postal_code: z.string().max(20),
});
type BranchValues = z.infer<typeof branchSchema>;

function toValues(b?: BranchDetail): BranchValues {
  return {
    name: b?.name ?? "",
    code: b?.code ?? "",
    phone: b?.phone ?? "",
    email: b?.email ?? "",
    address_line1: b?.address_line1 ?? "",
    address_line2: b?.address_line2 ?? "",
    city: b?.city ?? "",
    postal_code: b?.postal_code ?? "",
  };
}

export function BranchForm({ branch, readOnly = false }: { branch?: BranchDetail; readOnly?: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const form = useForm<BranchValues>({ resolver: zodResolver(branchSchema), defaultValues: toValues(branch) });
  const { errors, isSubmitting, isDirty } = form.formState;

  async function onSubmit(values: BranchValues) {
    setMessage(null);
    try {
      if (branch) {
        const updated = await api<BranchDetail>("PATCH", `/branches/${branch.id}`, nullIfBlank(values));
        form.reset(toValues(updated));
        setMessage({ tone: "success", text: "Branch saved." });
        router.refresh();
      } else {
        const created = await api<BranchDetail>("POST", "/branches", nullIfBlank(values));
        router.push(`/branches/${created.id}`);
      }
    } catch (e) {
      const text = applyApiError(form, e);
      if (text) setMessage({ tone: "error", text });
    }
  }

  const text = (name: keyof BranchValues, label: string, opts: { required?: boolean; hint?: string; type?: string } = {}) => (
    <Field label={label} required={opts.required} hint={opts.hint} error={errors[name]?.message}>
      {(p) => <Input {...p} type={opts.type ?? "text"} disabled={readOnly} {...form.register(name)} />}
    </Field>
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {text("name", "Branch name", { required: true })}
        {text("code", "Branch code", { required: true, hint: "Short code, e.g. WHK or SWK-01." })}
        {text("phone", "Phone", { type: "tel" })}
        {text("email", "Email", { type: "email" })}
        {text("address_line1", "Address line 1")}
        {text("address_line2", "Address line 2")}
        {text("city", "Town / city")}
        {text("postal_code", "Postal code")}
      </div>
      {readOnly ? null : (
        <Button type="submit" variant="primary" loading={isSubmitting} disabled={branch && !isDirty}>
          {branch ? "Save branch" : "Create branch"}
        </Button>
      )}
    </form>
  );
}

interface DayDraft {
  weekday: number;
  is_closed: boolean;
  opens_at: string;
  closes_at: string;
}

export function OperatingHoursForm({
  branchId,
  hours,
  readOnly,
}: {
  branchId: string;
  hours: OperatingHours[];
  readOnly: boolean;
}) {
  const router = useRouter();
  const initial: DayDraft[] = hours.map((h) => ({
    weekday: h.weekday,
    is_closed: h.is_closed,
    opens_at: shortTime(h.opens_at) || "08:00",
    closes_at: shortTime(h.closes_at) || "17:00",
  }));
  const [days, setDays] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);

  const invalid = days.some((d) => !d.is_closed && (!d.opens_at || !d.closes_at || d.opens_at >= d.closes_at));
  const dirty = JSON.stringify(days) !== JSON.stringify(initial);

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      await api("PUT", `/branches/${branchId}/operating-hours`, {
        days: days.map((d) => (d.is_closed ? { weekday: d.weekday, is_closed: true } : d)),
      });
      setMessage({ tone: "success", text: "Operating hours saved." });
      router.refresh();
    } catch (e) {
      setMessage({ tone: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  }

  const update = (weekday: number, patch: Partial<DayDraft>) =>
    setDays((prev) => prev.map((d) => (d.weekday === weekday ? { ...d, ...patch } : d)));

  return (
    <div className="space-y-3">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <ul className="divide-y divide-border">
        {days.map((d) => {
          const bad = !d.is_closed && d.opens_at >= d.closes_at;
          return (
            <li key={d.weekday} className="grid grid-cols-[6rem_1fr] items-center gap-2 py-2 sm:grid-cols-[7rem_6rem_1fr]">
              <span className="font-medium">{WEEKDAYS[d.weekday]}</span>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-steel"
                  checked={!d.is_closed}
                  disabled={readOnly}
                  onChange={(e) => update(d.weekday, { is_closed: !e.target.checked })}
                />
                Open
              </label>
              {d.is_closed ? (
                <span className="col-span-2 text-sm text-muted sm:col-span-1">Closed</span>
              ) : (
                <div className="col-span-2 flex items-center gap-2 sm:col-span-1">
                  <Input
                    type="time"
                    aria-label={`${WEEKDAYS[d.weekday]} opens`}
                    value={d.opens_at}
                    disabled={readOnly}
                    onChange={(e) => update(d.weekday, { opens_at: e.target.value })}
                    className="w-32"
                    aria-invalid={bad || undefined}
                  />
                  <span className="text-muted">to</span>
                  <Input
                    type="time"
                    aria-label={`${WEEKDAYS[d.weekday]} closes`}
                    value={d.closes_at}
                    disabled={readOnly}
                    onChange={(e) => update(d.weekday, { closes_at: e.target.value })}
                    className="w-32"
                    aria-invalid={bad || undefined}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {invalid ? <p className="text-xs font-medium text-status-danger">Closing time must be after opening time.</p> : null}
      {readOnly ? null : (
        <Button variant="primary" onClick={() => void save()} loading={busy} disabled={!dirty || invalid}>
          Save hours
        </Button>
      )}
    </div>
  );
}

export function ServiceBays({ branchId, bays, readOnly }: { branchId: string; bays: ServiceBay[]; readOnly: boolean }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api("POST", `/branches/${branchId}/service-bays`, { name });
      setName("");
      router.refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function setActive(bay: ServiceBay, active: boolean) {
    await api("PATCH", `/branches/${branchId}/service-bays/${bay.id}`, { is_active: active });
    router.refresh();
  }

  return (
    <div>
      {bays.length === 0 ? (
        <p className="px-4 py-4 text-sm text-muted">No service bays yet. Add the lifts, pits and work areas used for scheduling.</p>
      ) : (
        <ul className="divide-y divide-border">
          {bays.map((bay) => (
            <li key={bay.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
              <div>
                <p className={bay.is_active ? "font-medium" : "font-medium text-muted"}>{bay.name}</p>
                {bay.description ? <p className="text-xs text-muted">{bay.description}</p> : null}
              </div>
              <div className="flex items-center gap-2">
                {bay.is_active ? null : <StatusBadge tone="neutral">Retired</StatusBadge>}
                {readOnly ? null : bay.is_active ? (
                  <ConfirmButton
                    trigger={<Button size="sm">Retire</Button>}
                    title={`Retire ${bay.name}?`}
                    description="Retired bays cannot be booked. Past bookings keep their history."
                    confirmLabel="Retire bay"
                    onConfirm={() => setActive(bay, false)}
                  />
                ) : (
                  <Button size="sm" onClick={() => void setActive(bay, true)}>
                    Reinstate
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {readOnly ? null : (
        <form onSubmit={add} className="flex flex-col gap-2 border-t border-border p-4 sm:flex-row">
          <label htmlFor="new-bay" className="sr-only">
            New bay name
          </label>
          <Input id="new-bay" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bay 3 – 2-post lift" maxLength={100} />
          <Button type="submit" loading={busy} disabled={!name.trim()}>
            Add bay
          </Button>
          {error ? <p role="alert" className="text-sm text-status-danger sm:self-center">{error}</p> : null}
        </form>
      )}
    </div>
  );
}

export function ArchiveBranch({ branch }: { branch: BranchDetail }) {
  const router = useRouter();
  const archived = Boolean(branch.archived_at);
  return archived ? (
    <ConfirmButton
      trigger={<Button>Restore branch</Button>}
      title={`Restore ${branch.name}?`}
      description="Staff assigned to this branch regain access to it."
      confirmLabel="Restore"
      onConfirm={async () => {
        await api("POST", `/branches/${branch.id}/restore`);
        router.refresh();
      }}
    />
  ) : (
    <ConfirmButton
      trigger={<Button variant="danger">Archive branch</Button>}
      title={`Archive ${branch.name}?`}
      description="The branch is hidden and branch-only role assignments stop granting access. Records are kept and you can restore it later."
      confirmLabel="Archive"
      destructive
      onConfirm={async () => {
        await api("POST", `/branches/${branch.id}/archive`);
        router.refresh();
      }}
    />
  );
}
