"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { DocumentSequence, Organisation, OrganisationSettings, TaxRate } from "@/lib/api/types";
import { applyApiError, nullIfBlank } from "@/lib/forms";

type Message = { tone: "error" | "success"; text: string } | null;

// --------------------------------------------------------------------------- profile

const profileSchema = z.object({
  name: z.string().trim().min(1, "Enter the trading name.").max(200),
  legal_name: z.string().max(200),
  registration_number: z.string().max(100),
  tax_number: z.string().max(100),
  email: z.union([z.literal(""), z.email("Enter a valid email address.")]),
  phone: z.string().max(50),
  website: z.string().max(200),
  address_line1: z.string().max(200),
  address_line2: z.string().max(200),
  city: z.string().max(100),
  postal_code: z.string().max(20),
});
type ProfileValues = z.infer<typeof profileSchema>;

const profileFields: { name: keyof ProfileValues; label: string; hint?: string; type?: string }[] = [
  { name: "name", label: "Trading name" },
  { name: "legal_name", label: "Registered name" },
  { name: "registration_number", label: "Company registration number" },
  { name: "tax_number", label: "Tax / VAT number", hint: "Printed on quotations and invoices." },
  { name: "phone", label: "Phone", type: "tel" },
  { name: "email", label: "Email", type: "email" },
  { name: "website", label: "Website" },
  { name: "address_line1", label: "Address line 1" },
  { name: "address_line2", label: "Address line 2" },
  { name: "city", label: "Town / city" },
  { name: "postal_code", label: "Postal code" },
];

export function OrganisationForm({ organisation, readOnly }: { organisation: Organisation; readOnly: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState<Message>(null);
  const defaults = Object.fromEntries(
    profileFields.map((f) => [f.name, (organisation[f.name as keyof Organisation] as string | null) ?? ""]),
  ) as ProfileValues;
  const form = useForm<ProfileValues>({ resolver: zodResolver(profileSchema), defaultValues: defaults });
  const { errors, isSubmitting, isDirty } = form.formState;

  async function onSubmit(values: ProfileValues) {
    setMessage(null);
    try {
      await api("PATCH", "/organisation", nullIfBlank(values));
      form.reset(values);
      setMessage({ tone: "success", text: "Organisation details saved." });
      router.refresh();
    } catch (e) {
      const text = applyApiError(form, e);
      if (text) setMessage({ tone: "error", text });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {profileFields.map((f) => (
          <Field key={f.name} label={f.label} hint={f.hint} required={f.name === "name"} error={errors[f.name]?.message}>
            {(p) => <Input {...p} type={f.type ?? "text"} disabled={readOnly} {...form.register(f.name)} />}
          </Field>
        ))}
      </div>
      {readOnly ? null : (
        <Button type="submit" variant="primary" loading={isSubmitting} disabled={!isDirty}>
          Save details
        </Button>
      )}
    </form>
  );
}

// --------------------------------------------------------------------------- preferences

const TIMEZONES = ["Africa/Windhoek", "Africa/Johannesburg", "Africa/Gaborone", "Africa/Lusaka", "Africa/Harare", "UTC"];

const prefsSchema = z.object({
  currency_code: z.string().regex(/^[A-Z]{3}$/, "Use a 3-letter ISO code, e.g. NAD."),
  timezone: z.string().min(1),
  date_format: z.enum(["DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"]),
  prices_include_tax: z.boolean(),
  document_footer: z.string().max(1000),
  quotation_validity_days: z
    .string()
    .regex(/^\d{1,3}$/, "Whole days only.")
    .refine((v) => Number(v) >= 1 && Number(v) <= 365, "Between 1 and 365 days."),
  quotation_terms: z.string().max(4000),
});
type PrefsValues = z.infer<typeof prefsSchema>;

export function PreferencesForm({ settings, readOnly }: { settings: OrganisationSettings; readOnly: boolean }) {
  const router = useRouter();
  const [message, setMessage] = useState<Message>(null);
  const form = useForm<PrefsValues>({
    resolver: zodResolver(prefsSchema),
    defaultValues: {
      ...settings,
      document_footer: settings.document_footer ?? "",
      quotation_validity_days: String(settings.quotation_validity_days),
      quotation_terms: settings.quotation_terms ?? "",
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  const timezones = TIMEZONES.includes(settings.timezone) ? TIMEZONES : [settings.timezone, ...TIMEZONES];

  async function onSubmit(values: PrefsValues) {
    setMessage(null);
    try {
      await api("PATCH", "/organisation/settings", {
        ...values,
        document_footer: values.document_footer.trim() || null,
        quotation_validity_days: Number(values.quotation_validity_days),
        quotation_terms: values.quotation_terms.trim() || null,
      });
      form.reset(values);
      setMessage({ tone: "success", text: "Preferences saved." });
      router.refresh();
    } catch (e) {
      const text = applyApiError(form, e);
      if (text) setMessage({ tone: "error", text });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Currency" error={errors.currency_code?.message} hint="Namibian Dollar is NAD.">
          {(p) => <Input {...p} disabled={readOnly} maxLength={3} {...form.register("currency_code")} />}
        </Field>
        <Field label="Time zone" error={errors.timezone?.message}>
          {(p) => (
            <Select {...p} disabled={readOnly} {...form.register("timezone")}>
              {timezones.map((tz) => (
                <option key={tz}>{tz}</option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Date format" error={errors.date_format?.message}>
          {(p) => (
            <Select {...p} disabled={readOnly} {...form.register("date_format")}>
              <option value="DD/MM/YYYY">DD/MM/YYYY (31/12/2026)</option>
              <option value="YYYY-MM-DD">YYYY-MM-DD (2026-12-31)</option>
              <option value="MM/DD/YYYY">MM/DD/YYYY (12/31/2026)</option>
            </Select>
          )}
        </Field>
      </div>
      <Checkbox
        label="Prices include tax"
        description="When on, labour and part prices you enter already include tax. Confirm the right setting with your accountant."
        disabled={readOnly}
        {...form.register("prices_include_tax")}
      />
      <Field label="Document footer" hint="Printed at the bottom of quotations and invoices, e.g. banking details." error={errors.document_footer?.message}>
        {(p) => <Textarea {...p} rows={3} disabled={readOnly} {...form.register("document_footer")} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Quotations valid for (days)" error={errors.quotation_validity_days?.message}>
          {(p) => <Input {...p} type="number" min={1} max={365} disabled={readOnly} {...form.register("quotation_validity_days")} />}
        </Field>
      </div>
      <Field label="Default quotation terms" hint="Copied onto new quotations; editable per quotation." error={errors.quotation_terms?.message}>
        {(p) => <Textarea {...p} rows={3} disabled={readOnly} {...form.register("quotation_terms")} />}
      </Field>
      {readOnly ? null : (
        <Button type="submit" variant="primary" loading={isSubmitting} disabled={!isDirty}>
          Save preferences
        </Button>
      )}
    </form>
  );
}

// --------------------------------------------------------------------------- tax rates

const taxSchema = z.object({
  name: z.string().trim().min(1, "Enter a name.").max(100),
  rate_percent: z
    .string()
    .trim()
    .regex(/^\d{1,3}(\.\d{1,2})?$/, "Enter a percentage with up to 2 decimals.")
    .refine((v) => Number(v) <= 100, "Cannot exceed 100%."),
  description: z.string().max(300),
  is_default: z.boolean(),
  is_active: z.boolean(),
});
type TaxValues = z.infer<typeof taxSchema>;

export function TaxRateDialog({ rate, trigger }: { rate?: TaxRate; trigger: (open: () => void) => React.ReactNode }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<TaxValues>({
    resolver: zodResolver(taxSchema),
    defaultValues: {
      name: rate?.name ?? "",
      rate_percent: rate?.rate_percent ?? "",
      description: rate?.description ?? "",
      is_default: rate?.is_default ?? false,
      is_active: rate?.is_active ?? true,
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: TaxValues) {
    setError(null);
    const body = { ...values, description: values.description.trim() || null };
    try {
      if (rate) {
        await api("PATCH", `/organisation/tax-rates/${rate.id}`, body);
      } else {
        await api("POST", "/organisation/tax-rates", {
          name: body.name,
          rate_percent: body.rate_percent,
          description: body.description,
          is_default: body.is_default,
        });
        form.reset();
      }
      setOpen(false);
      router.refresh();
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  return (
    <>
      {trigger(() => setOpen(true))}
      <Dialog open={open} onOpenChange={setOpen} title={rate ? `Edit ${rate.name}` : "Add tax rate"}>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Name" required error={errors.name?.message} hint="e.g. Standard VAT, Zero-rated">
            {(p) => <Input {...p} {...form.register("name")} />}
          </Field>
          <Field label="Rate (%)" required error={errors.rate_percent?.message}>
            {(p) => <Input {...p} inputMode="decimal" className="font-mono" {...form.register("rate_percent")} />}
          </Field>
          <Field label="Description" error={errors.description?.message}>
            {(p) => <Input {...p} {...form.register("description")} />}
          </Field>
          <Checkbox label="Default rate" description="Pre-selected on new quotation and invoice lines." {...form.register("is_default")} />
          {rate ? <Checkbox label="Active" description="Inactive rates cannot be selected on new documents." {...form.register("is_active")} /> : null}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={isSubmitting}>
              {rate ? "Save" : "Add rate"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function TaxRateRow({ rate, canManage }: { rate: TaxRate; canManage: boolean }) {
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className={rate.is_active ? "font-medium" : "font-medium text-muted"}>{rate.name}</p>
        {rate.description ? <p className="text-xs text-muted">{rate.description}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {rate.is_default ? <StatusBadge tone="active">Default</StatusBadge> : null}
        {rate.is_active ? null : <StatusBadge tone="neutral">Inactive</StatusBadge>}
        <span className="w-16 text-right font-mono tabular-nums">{rate.rate_percent}%</span>
        {canManage ? (
          <TaxRateDialog rate={rate} trigger={(open) => <Button size="sm" onClick={open}>Edit</Button>} />
        ) : null}
      </div>
    </li>
  );
}

// --------------------------------------------------------------------------- numbering

export function SequenceRow({ sequence, canManage }: { sequence: DocumentSequence; canManage: boolean }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [prefix, setPrefix] = useState(sequence.prefix);
  const [nextNumber, setNextNumber] = useState(String(sequence.next_number));
  const [padding, setPadding] = useState(String(sequence.padding));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const preview = `${prefix ? `${prefix}-` : ""}${(nextNumber || "0").padStart(Number(padding) || 1, "0")}`;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("PATCH", `/organisation/document-sequences/${sequence.document_type}`, {
        prefix,
        next_number: Number(nextNumber),
        padding: Number(padding),
      });
      setEditing(false);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <li className="flex items-center justify-between gap-3 px-4 py-3">
        <div>
          <p className="font-medium">{sequence.label}</p>
          <p className="text-xs text-muted">Next number</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono tabular-nums">{sequence.example}</span>
          {canManage ? (
            <Button size="sm" onClick={() => setEditing(true)}>
              Edit
            </Button>
          ) : null}
        </div>
      </li>
    );
  }

  return (
    <li className="space-y-3 bg-mist/50 px-4 py-3">
      <p className="font-medium">{sequence.label}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Prefix" hint="Capitals, digits, hyphens. Up to 10.">
          {(p) => <Input {...p} value={prefix} maxLength={10} onChange={(e) => setPrefix(e.target.value.toUpperCase())} className="font-mono" />}
        </Field>
        <Field label="Next number" hint={`Cannot be lower than ${sequence.next_number}.`}>
          {(p) => <Input {...p} type="number" min={sequence.next_number} value={nextNumber} onChange={(e) => setNextNumber(e.target.value)} className="font-mono" />}
        </Field>
        <Field label="Digits">
          {(p) => <Input {...p} type="number" min={1} max={10} value={padding} onChange={(e) => setPadding(e.target.value)} className="font-mono" />}
        </Field>
      </div>
      <p className="text-sm">
        Preview: <span className="font-mono">{preview}</span>
      </p>
      <div className="flex gap-2">
        <Button variant="primary" loading={busy} onClick={() => void save()}>
          Save
        </Button>
        <Button
          onClick={() => {
            setEditing(false);
            setPrefix(sequence.prefix);
            setNextNumber(String(sequence.next_number));
            setPadding(String(sequence.padding));
            setError(null);
          }}
        >
          Cancel
        </Button>
      </div>
    </li>
  );
}
