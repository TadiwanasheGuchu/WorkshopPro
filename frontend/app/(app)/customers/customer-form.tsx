"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { CustomerDetail } from "@/lib/api/types";
import { applyApiError } from "@/lib/forms";
import { CONTACT_METHOD } from "@/lib/labels";

const contactSchema = z.object({
  kind: z.enum(["phone", "email"]),
  // Empty rows are allowed and dropped on submit (the form starts with one blank phone row).
  value: z.string().trim(),
  label: z.string().max(50),
  is_primary: z.boolean(),
});

const schema = z
  .object({
    customer_type: z.enum(["individual", "company"]),
    first_name: z.string().max(200),
    last_name: z.string().max(200),
    company_name: z.string().max(200),
    contact_person: z.string().max(200),
    registration_number: z.string().max(100),
    tax_number: z.string().max(100),
    preferred_contact_method: z.enum(["phone", "whatsapp", "email", "sms"]),
    notes: z.string().max(4000),
    contacts: z.array(contactSchema).max(10),
    address_line1: z.string().max(200),
    address_line2: z.string().max(200),
    address_city: z.string().max(100),
    address_postal_code: z.string().max(20),
  })
  .superRefine((v, ctx) => {
    if (v.customer_type === "individual" && !v.last_name.trim())
      ctx.addIssue({ code: "custom", path: ["last_name"], message: "Enter the surname." });
    if (v.customer_type === "company" && !v.company_name.trim())
      ctx.addIssue({ code: "custom", path: ["company_name"], message: "Enter the company name." });
    v.contacts.forEach((c, i) => {
      if (c.kind === "email" && c.value && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.value.trim()))
        ctx.addIssue({ code: "custom", path: ["contacts", i, "value"], message: "Enter a valid email address." });
      if (c.kind === "phone" && c.value && (c.value.replace(/\D/g, "").length < 6 || c.value.replace(/\D/g, "").length > 15))
        ctx.addIssue({ code: "custom", path: ["contacts", i, "value"], message: "Enter 6 to 15 digits." });
    });
  });
type Values = z.infer<typeof schema>;

function defaults(c?: CustomerDetail): Values {
  const physical = c?.addresses.find((a) => a.kind === "physical");
  return {
    customer_type: c?.customer_type ?? "individual",
    first_name: c?.first_name ?? "",
    last_name: c?.last_name ?? "",
    company_name: c?.company_name ?? "",
    contact_person: c?.contact_person ?? "",
    registration_number: c?.registration_number ?? "",
    tax_number: c?.tax_number ?? "",
    preferred_contact_method: c?.preferred_contact_method ?? "phone",
    notes: c?.notes ?? "",
    contacts: c?.contacts.length
      ? c.contacts.map((x) => ({ kind: x.kind, value: x.value, label: x.label ?? "", is_primary: x.is_primary }))
      : [{ kind: "phone", value: "", label: "Mobile", is_primary: true }],
    address_line1: physical?.line1 ?? "",
    address_line2: physical?.line2 ?? "",
    address_city: physical?.city ?? "",
    address_postal_code: physical?.postal_code ?? "",
  };
}

const blank = (v: string) => (v.trim() ? v.trim() : null);

function toBody(v: Values, existing?: CustomerDetail) {
  const company = v.customer_type === "company";
  const postal = existing?.addresses.filter((a) => a.kind === "postal") ?? [];
  return {
    customer_type: v.customer_type,
    first_name: company ? null : blank(v.first_name),
    last_name: company ? null : blank(v.last_name),
    company_name: company ? blank(v.company_name) : null,
    contact_person: company ? blank(v.contact_person) : null,
    registration_number: company ? blank(v.registration_number) : null,
    tax_number: blank(v.tax_number),
    preferred_contact_method: v.preferred_contact_method,
    notes: blank(v.notes),
    contacts: v.contacts
      .filter((c) => c.value.trim())
      .map((c) => ({ kind: c.kind, value: c.value.trim(), label: blank(c.label), is_primary: c.is_primary })),
    addresses: [
      ...(v.address_line1.trim()
        ? [
            {
              kind: "physical",
              line1: v.address_line1.trim(),
              line2: blank(v.address_line2),
              city: blank(v.address_city),
              postal_code: blank(v.address_postal_code),
            },
          ]
        : []),
      // Postal addresses are kept as they are (not edited on this form yet).
      ...postal.map(({ kind, line1, line2, city, region, postal_code }) => ({ kind, line1, line2, city, region, postal_code })),
    ],
  };
}

export function CustomerForm({ customer }: { customer?: CustomerDetail }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: defaults(customer) });
  const contacts = useFieldArray({ control: form.control, name: "contacts" });
  const type = useWatch({ control: form.control, name: "customer_type" });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const body = toBody(values, customer);
      const saved = customer
        ? await api<CustomerDetail>("PATCH", `/customers/${customer.id}`, body)
        : await api<CustomerDetail>("POST", "/customers", body);
      router.push(`/customers/${saved.id}`);
      router.refresh();
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  const text = (name: keyof Values, label: string, opts: { required?: boolean; autoComplete?: string } = {}) => (
    <Field label={label} required={opts.required} error={(errors[name] as { message?: string } | undefined)?.message}>
      {(p) => <Input {...p} autoComplete={opts.autoComplete ?? "off"} {...form.register(name)} />}
    </Field>
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="max-w-3xl space-y-6">
      {error ? <Alert tone="error">{error}</Alert> : null}

      <fieldset>
        <legend className="mb-2 text-sm font-medium">Customer type</legend>
        <div className="inline-flex rounded-control border border-border bg-surface p-0.5" role="radiogroup">
          {(["individual", "company"] as const).map((t) => (
            <label
              key={t}
              className={`cursor-pointer rounded-control px-4 py-2 text-sm ${type === t ? "bg-steel font-medium text-white" : "text-slate-deep"}`}
            >
              <input type="radio" value={t} className="sr-only" {...form.register("customer_type")} />
              {t === "individual" ? "Individual" : "Company"}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        {type === "individual" ? (
          <>
            {text("first_name", "First name", { autoComplete: "off" })}
            {text("last_name", "Surname", { required: true })}
          </>
        ) : (
          <>
            {text("company_name", "Company name", { required: true })}
            {text("contact_person", "Contact person")}
            {text("registration_number", "Company registration number")}
          </>
        )}
        {text("tax_number", "Tax / VAT number")}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Phone numbers and email</legend>
        {contacts.fields.map((field, index) => {
          const err = errors.contacts?.[index]?.value?.message;
          return (
            <div key={field.id} className="grid grid-cols-[7.5rem_1fr_auto] items-start gap-2 sm:grid-cols-[7.5rem_1fr_9rem_auto]">
              <Select aria-label={`Contact ${index + 1} type`} {...form.register(`contacts.${index}.kind`)}>
                <option value="phone">Phone</option>
                <option value="email">Email</option>
              </Select>
              <div>
                <Input
                  aria-label={`Contact ${index + 1}`}
                  aria-invalid={err ? true : undefined}
                  inputMode={form.getValues(`contacts.${index}.kind`) === "phone" ? "tel" : "email"}
                  {...form.register(`contacts.${index}.value`)}
                />
                {err ? <p className="mt-1 text-xs font-medium text-status-danger">{err}</p> : null}
              </div>
              <Input aria-label={`Contact ${index + 1} label`} placeholder="Label" className="hidden sm:block" {...form.register(`contacts.${index}.label`)} />
              <Button variant="ghost" aria-label={`Remove contact ${index + 1}`} onClick={() => contacts.remove(index)}>
                <X className="size-4" aria-hidden />
              </Button>
            </div>
          );
        })}
        <div className="flex gap-2">
          <Button size="sm" onClick={() => contacts.append({ kind: "phone", value: "", label: "", is_primary: false })}>
            <Plus className="size-4" aria-hidden /> Phone
          </Button>
          <Button size="sm" onClick={() => contacts.append({ kind: "email", value: "", label: "", is_primary: false })}>
            <Plus className="size-4" aria-hidden /> Email
          </Button>
        </div>
        <p className="text-xs text-muted">The first phone number and first email are used as primary.</p>
      </fieldset>

      <Field label="Preferred contact method">
        {(p) => (
          <Select {...p} className="sm:max-w-xs" {...form.register("preferred_contact_method")}>
            {Object.entries(CONTACT_METHOD).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">Physical address</legend>
        {text("address_line1", "Street address")}
        {text("address_line2", "Suburb / area")}
        {text("address_city", "Town / city")}
        {text("address_postal_code", "Postal code")}
      </fieldset>

      <Field label="Notes" error={errors.notes?.message}>
        {(p) => <Textarea {...p} rows={3} {...form.register("notes")} />}
      </Field>

      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          {customer ? "Save customer" : "Register customer"}
        </Button>
        <Button onClick={() => router.back()}>Cancel</Button>
      </div>
    </form>
  );
}
