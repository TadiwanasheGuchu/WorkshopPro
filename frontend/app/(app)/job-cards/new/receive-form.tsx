"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { CustomerPicker } from "@/components/app/customer-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api/client";
import type { BranchSummary, JobCardDetail, Page, ServiceBay, Vehicle } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { applyApiError } from "@/lib/forms";
import { FUEL_LEVEL_LABEL, PRIORITY_LABEL } from "@/lib/job-status";
import { formatKm, vehicleTitle } from "@/lib/labels";

const schema = z
  .object({
    branch_id: z.string().min(1, "Choose a branch."),
    customer: z.object({ id: z.string(), display_name: z.string() }).nullable(),
    vehicle_id: z.string(),
    complaint: z.string().trim().min(1, "Describe what the customer reports.").max(4000),
    requested_work: z.string().max(4000),
    intake_odometer_km: z.string().refine((v) => !v || /^\d{1,7}$/.test(v.replace(/\s/g, "")), "Whole kilometres only."),
    odometer_correction_reason: z.string().max(300),
    fuel_level: z.string(),
    priority: z.enum(["low", "normal", "high", "urgent"]),
    promised_at: z.string(),
    service_bay_id: z.string(),
  })
  .superRefine((v, ctx) => {
    if (!v.customer) ctx.addIssue({ code: "custom", path: ["customer"], message: "Choose the customer." });
    if (!v.vehicle_id) ctx.addIssue({ code: "custom", path: ["vehicle_id"], message: "Choose the vehicle." });
  });
type Values = z.infer<typeof schema>;

function Segmented<T extends string>({
  name,
  value,
  onChange,
  options,
}: {
  name: string;
  value: string;
  onChange: (v: T | "") => void;
  options: [T, string][];
}) {
  return (
    <div role="radiogroup" aria-label={name} className="flex flex-wrap gap-1.5">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(value === v ? "" : v)}
          className={cn(
            "h-10 min-w-12 rounded-control border px-3 text-sm",
            value === v ? "border-steel bg-steel font-medium text-white" : "border-border bg-surface hover:bg-mist",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function ReceiveForm({
  branches,
  initialVehicle,
}: {
  branches: BranchSummary[];
  initialVehicle: Vehicle | null;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [openJob, setOpenJob] = useState<string | null>(null);
  const [needsReason, setNeedsReason] = useState(false);
  const [vehicles, setVehicles] = useState<Vehicle[]>(initialVehicle ? [initialVehicle] : []);
  const [bays, setBays] = useState<ServiceBay[]>([]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      branch_id: branches.length === 1 ? branches[0].id : "",
      customer: initialVehicle ? { id: initialVehicle.customer.id, display_name: initialVehicle.customer.display_name } : null,
      vehicle_id: initialVehicle?.id ?? "",
      complaint: "",
      requested_work: "",
      intake_odometer_km: "",
      odometer_correction_reason: "",
      fuel_level: "",
      priority: "normal",
      promised_at: "",
      service_bay_id: "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const customer = useWatch({ control: form.control, name: "customer" });
  const branchId = useWatch({ control: form.control, name: "branch_id" });
  const vehicleId = useWatch({ control: form.control, name: "vehicle_id" });
  const selectedVehicle = vehicles.find((v) => v.id === vehicleId);

  useEffect(() => {
    if (!customer) return;
    let cancelled = false;
    api<Page<Vehicle>>("GET", `/vehicles?customer_id=${customer.id}&page_size=50`)
      .then((page) => {
        if (cancelled) return;
        setVehicles(page.items);
        const current = form.getValues("vehicle_id");
        if (!page.items.some((v) => v.id === current)) {
          form.setValue("vehicle_id", page.items.length === 1 ? page.items[0].id : "");
        }
      })
      .catch(() => !cancelled && setVehicles([]));
    return () => {
      cancelled = true;
    };
  }, [customer, form]);

  useEffect(() => {
    if (!branchId) return;
    let cancelled = false;
    api<ServiceBay[]>("GET", `/branches/${branchId}/service-bays`)
      .then((items) => !cancelled && setBays(items.filter((b) => b.is_active)))
      .catch(() => !cancelled && setBays([]));
    return () => {
      cancelled = true;
    };
  }, [branchId]);

  async function onSubmit(v: Values) {
    setError(null);
    setOpenJob(null);
    try {
      const job = await api<JobCardDetail>("POST", "/job-cards", {
        branch_id: v.branch_id,
        customer_id: v.customer?.id,
        vehicle_id: v.vehicle_id,
        complaint: v.complaint.trim(),
        requested_work: v.requested_work.trim() || null,
        intake_odometer_km: v.intake_odometer_km ? Number(v.intake_odometer_km.replace(/\s/g, "")) : null,
        odometer_correction_reason: needsReason ? v.odometer_correction_reason.trim() || null : null,
        fuel_level: v.fuel_level || null,
        priority: v.priority,
        // datetime-local is in the device's time zone; workshop devices use local time.
        promised_at: v.promised_at ? new Date(v.promised_at).toISOString() : null,
        service_bay_id: v.service_bay_id || null,
      });
      router.push(`/job-cards/${job.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "odometer_decrease") {
        setNeedsReason(true);
        form.setError("intake_odometer_km", { message: e.message });
        return;
      }
      if (e instanceof ApiError && e.details && typeof e.details === "object" && "open_job_number" in e.details) {
        setOpenJob(String((e.details as { open_job_number: string }).open_job_number));
      }
      setError(applyApiError(form, e));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="max-w-3xl space-y-6">
      {error ? (
        <Alert tone="error">
          {error}
          {openJob ? (
            <Link href={`/job-cards?search=${openJob}`} className="ml-1 text-steel underline">
              Open {openJob}
            </Link>
          ) : null}
        </Alert>
      ) : null}

      {branches.length > 1 ? (
        <Field label="Branch" required error={errors.branch_id?.message}>
          {(p) => (
            <Select {...p} {...form.register("branch_id")}>
              <option value="">Choose branch</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : null}

      <Field label="Customer" required error={errors.customer?.message}>
        {(p) => (
          <Controller
            control={form.control}
            name="customer"
            render={({ field }) => (
              <CustomerPicker inputId={p.id} value={field.value} onChange={field.onChange} invalid={Boolean(errors.customer)} />
            )}
          />
        )}
      </Field>
      {!customer ? (
        <p className="-mt-4 text-sm">
          New customer?{" "}
          <Link href="/customers/new" className="text-steel hover:underline">
            Register them first
          </Link>
          .
        </p>
      ) : null}

      {customer ? (
        <Field label="Vehicle" required error={errors.vehicle_id?.message}>
          {(p) =>
            vehicles.length ? (
              <Select {...p} {...form.register("vehicle_id")}>
                <option value="">Choose vehicle</option>
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {vehicleTitle(v)} · {[v.year, v.make, v.model].filter(Boolean).join(" ")}
                  </option>
                ))}
              </Select>
            ) : (
              <p className="text-sm">
                No vehicles registered.{" "}
                <Link href={`/vehicles/new?customer_id=${customer.id}`} className="text-steel hover:underline">
                  Register a vehicle
                </Link>
              </p>
            )
          }
        </Field>
      ) : null}

      {selectedVehicle?.existing_damage ? (
        <Alert tone="info" title="Existing damage on record">
          {selectedVehicle.existing_damage}
        </Alert>
      ) : null}

      <Field label="Customer complaint" required hint="In the customer's words, e.g. grinding noise when braking." error={errors.complaint?.message}>
        {(p) => <Textarea {...p} rows={3} {...form.register("complaint")} />}
      </Field>
      <Field label="Requested work" hint="Anything specific the customer asked for, e.g. 60 000 km service.">
        {(p) => <Textarea {...p} rows={2} {...form.register("requested_work")} />}
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Odometer at intake (km)"
          hint={selectedVehicle?.odometer_km != null ? `Last recorded ${formatKm(selectedVehicle.odometer_km)}` : undefined}
          error={errors.intake_odometer_km?.message}
        >
          {(p) => <Input {...p} inputMode="numeric" autoComplete="off" {...form.register("intake_odometer_km")} />}
        </Field>
        {needsReason ? (
          <Field label="Reason for lower reading" required>
            {(p) => <Input {...p} {...form.register("odometer_correction_reason")} />}
          </Field>
        ) : null}
        <Field label="Promised for" hint="When the customer expects the vehicle back.">
          {(p) => <Input {...p} type="datetime-local" {...form.register("promised_at")} />}
        </Field>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Fuel level</legend>
        <Controller
          control={form.control}
          name="fuel_level"
          render={({ field }) => (
            <Segmented name="Fuel level" value={field.value} onChange={field.onChange} options={Object.entries(FUEL_LEVEL_LABEL) as [string, string][]} />
          )}
        />
      </fieldset>
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Priority</legend>
        <Controller
          control={form.control}
          name="priority"
          render={({ field }) => (
            <Segmented
              name="Priority"
              value={field.value}
              onChange={(v) => field.onChange(v || "normal")}
              options={Object.entries(PRIORITY_LABEL) as [string, string][]}
            />
          )}
        />
      </fieldset>

      {bays.length ? (
        <Field label="Service bay">
          {(p) => (
            <Select {...p} className="sm:max-w-xs" {...form.register("service_bay_id")}>
              <option value="">Not yet allocated</option>
              {bays.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          Open job card
        </Button>
        <Button onClick={() => router.back()}>Cancel</Button>
      </div>
    </form>
  );
}
