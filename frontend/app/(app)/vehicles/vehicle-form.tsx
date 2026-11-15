"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { CustomerPicker, type PickedCustomer } from "@/components/app/customer-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ApiError, api } from "@/lib/api/client";
import type { Vehicle } from "@/lib/api/types";
import { applyApiError } from "@/lib/forms";
import { FUEL_TYPE, TRANSMISSION } from "@/lib/labels";

const nextYear = new Date().getFullYear() + 1;

const schema = z
  .object({
    customer: z.object({ id: z.string(), display_name: z.string() }).nullable(),
    registration_number: z.string().max(15),
    vin: z.string().max(20),
    engine_number: z.string().max(50),
    make: z.string().trim().min(1, "Enter the make.").max(60),
    model: z.string().trim().min(1, "Enter the model.").max(60),
    variant: z.string().max(100),
    year: z.string().refine((v) => !v || (Number(v) >= 1900 && Number(v) <= nextYear), `Year must be 1900–${nextYear}.`),
    fuel_type: z.string(),
    transmission: z.string(),
    colour: z.string().max(40),
    odometer_km: z.string().refine((v) => !v || /^\d{1,7}$/.test(v.replace(/\s/g, "")), "Enter kilometres as a whole number."),
    odometer_correction_reason: z.string().max(300),
    existing_damage: z.string().max(4000),
    notes: z.string().max(4000),
  })
  .superRefine((v, ctx) => {
    if (!v.customer) ctx.addIssue({ code: "custom", path: ["customer"], message: "Choose the owner." });
    if (!v.registration_number.trim() && !v.vin.trim())
      ctx.addIssue({ code: "custom", path: ["registration_number"], message: "Enter a registration or a VIN / chassis number." });
  });
type Values = z.infer<typeof schema>;

const blank = (v: string) => (v.trim() ? v.trim() : null);

export function VehicleForm({ vehicle, customer }: { vehicle?: Vehicle; customer?: PickedCustomer | null }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [needsReason, setNeedsReason] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      customer: vehicle ? vehicle.customer : (customer ?? null),
      registration_number: vehicle?.registration_number ?? "",
      vin: vehicle?.vin ?? "",
      engine_number: vehicle?.engine_number ?? "",
      make: vehicle?.make ?? "",
      model: vehicle?.model ?? "",
      variant: vehicle?.variant ?? "",
      year: vehicle?.year ? String(vehicle.year) : "",
      fuel_type: vehicle?.fuel_type ?? "",
      transmission: vehicle?.transmission ?? "",
      colour: vehicle?.colour ?? "",
      odometer_km: vehicle?.odometer_km != null ? String(vehicle.odometer_km) : "",
      odometer_correction_reason: "",
      existing_damage: vehicle?.existing_damage ?? "",
      notes: vehicle?.notes ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const regValue = useWatch({ control: form.control, name: "registration_number" });

  async function onSubmit(v: Values) {
    setError(null);
    const body = {
      registration_number: blank(v.registration_number),
      vin: blank(v.vin),
      engine_number: blank(v.engine_number),
      make: v.make.trim(),
      model: v.model.trim(),
      variant: blank(v.variant),
      year: v.year ? Number(v.year) : null,
      fuel_type: v.fuel_type || null,
      transmission: v.transmission || null,
      colour: blank(v.colour),
      odometer_km: v.odometer_km ? Number(v.odometer_km.replace(/\s/g, "")) : null,
      existing_damage: blank(v.existing_damage),
      notes: blank(v.notes),
    };
    try {
      const saved = vehicle
        ? await api<Vehicle>("PATCH", `/vehicles/${vehicle.id}`, {
            ...body,
            ...(needsReason ? { odometer_correction_reason: blank(v.odometer_correction_reason) } : {}),
          })
        : await api<Vehicle>("POST", "/vehicles", { ...body, customer_id: v.customer?.id });
      router.push(`/vehicles/${saved.id}`);
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === "odometer_decrease") {
        setNeedsReason(true);
        form.setError("odometer_correction_reason", { message: e.message });
        return;
      }
      setError(applyApiError(form, e));
    }
  }

  const text = (name: keyof Values, label: string, opts: { hint?: string; mono?: boolean; inputMode?: "numeric" } = {}) => (
    <Field label={label} hint={opts.hint} error={(errors[name] as { message?: string } | undefined)?.message}>
      {(p) => (
        <Input {...p} inputMode={opts.inputMode} autoComplete="off" className={opts.mono ? "font-mono uppercase" : undefined} {...form.register(name)} />
      )}
    </Field>
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="max-w-3xl space-y-6">
      {error ? <Alert tone="error">{error}</Alert> : null}

      {vehicle ? null : (
        <Field label="Owner" required error={errors.customer?.message}>
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
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {text("registration_number", "Registration number", { hint: "As on the number plate, e.g. N 12345 W.", mono: true })}
        {text("vin", "VIN / chassis number", { hint: regValue ? "Optional, but helps identify the vehicle." : "Required when there is no registration.", mono: true })}
        {text("make", "Make")}
        {text("model", "Model")}
        {text("variant", "Variant", { hint: "e.g. 2.8 GD-6 Raider D/C" })}
        {text("year", "Year", { inputMode: "numeric" })}
        <Field label="Fuel">
          {(p) => (
            <Select {...p} {...form.register("fuel_type")}>
              <option value="">Not recorded</option>
              {Object.entries(FUEL_TYPE).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Transmission">
          {(p) => (
            <Select {...p} {...form.register("transmission")}>
              <option value="">Not recorded</option>
              {Object.entries(TRANSMISSION).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {text("colour", "Colour")}
        {text("engine_number", "Engine number", { mono: true })}
        {text("odometer_km", "Odometer (km)", { inputMode: "numeric" })}
        {needsReason ? (
          <Field label="Reason for lower reading" required error={errors.odometer_correction_reason?.message}>
            {(p) => <Input {...p} {...form.register("odometer_correction_reason")} />}
          </Field>
        ) : null}
      </div>

      <Field label="Existing damage" hint="Scratches, dents and cracks present before the workshop received the vehicle.">
        {(p) => <Textarea {...p} rows={3} {...form.register("existing_damage")} />}
      </Field>
      <Field label="Notes">
        {(p) => <Textarea {...p} rows={2} {...form.register("notes")} />}
      </Field>

      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          {vehicle ? "Save vehicle" : "Register vehicle"}
        </Button>
        <Button onClick={() => router.back()}>Cancel</Button>
      </div>
    </form>
  );
}
