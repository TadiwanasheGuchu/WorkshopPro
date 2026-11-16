"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { Supplier } from "@/lib/api/types";
import { applyApiError } from "@/lib/forms";

const schema = z.object({
  name: z.string().trim().min(1, "Enter the supplier's name.").max(200),
  contact_person: z.string().max(200),
  phone: z.string().max(50),
  email: z.union([z.literal(""), z.email("Enter a valid email address.")]),
  address: z.string().max(1000),
  tax_number: z.string().max(100),
  account_number: z.string().max(100),
  payment_terms_days: z
    .string()
    .regex(/^\d{1,3}$/, "Whole days only.")
    .refine((v) => Number(v) <= 365, "At most 365 days."),
  notes: z.string().max(4000),
});
type Values = z.infer<typeof schema>;

const blank = (v: string) => (v.trim() ? v.trim() : null);

export function SupplierForm({ supplier }: { supplier?: Supplier }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: supplier?.name ?? "",
      contact_person: supplier?.contact_person ?? "",
      phone: supplier?.phone ?? "",
      email: supplier?.email ?? "",
      address: supplier?.address ?? "",
      tax_number: supplier?.tax_number ?? "",
      account_number: supplier?.account_number ?? "",
      payment_terms_days: String(supplier?.payment_terms_days ?? 30),
      notes: supplier?.notes ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    setError(null);
    const body = {
      name: v.name.trim(),
      contact_person: blank(v.contact_person),
      phone: blank(v.phone),
      email: blank(v.email),
      address: blank(v.address),
      tax_number: blank(v.tax_number),
      account_number: blank(v.account_number),
      payment_terms_days: Number(v.payment_terms_days),
      notes: blank(v.notes),
    };
    try {
      const saved = supplier ? await api<Supplier>("PATCH", `/suppliers/${supplier.id}`, body) : await api<Supplier>("POST", "/suppliers", body);
      router.push(`/suppliers/${saved.id}`);
      router.refresh();
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  const text = (name: keyof Values, label: string, opts: { hint?: string; type?: string; inputMode?: "numeric" | "email" | "tel" } = {}) => (
    <Field label={label} error={errors[name]?.message} hint={opts.hint} required={name === "name"}>
      {(p) => <Input {...p} type={opts.type} inputMode={opts.inputMode} {...form.register(name)} />}
    </Field>
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5" noValidate>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {text("name", "Name")}
      <div className="grid gap-4 sm:grid-cols-3">
        {text("contact_person", "Contact person")}
        {text("phone", "Phone", { type: "tel", inputMode: "tel" })}
        {text("email", "Email", { type: "email", inputMode: "email" })}
      </div>
      <Field label="Address" error={errors.address?.message}>
        {(p) => <Textarea {...p} rows={3} {...form.register("address")} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        {text("account_number", "Our account number", { hint: "Your account with this supplier." })}
        {text("tax_number", "Tax number")}
        {text("payment_terms_days", "Payment terms (days)", { inputMode: "numeric" })}
      </div>
      <Field label="Notes" error={errors.notes?.message}>
        {(p) => <Textarea {...p} rows={3} {...form.register("notes")} />}
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          {supplier ? "Save supplier" : "Add supplier"}
        </Button>
        <Button type="button" onClick={() => router.back()}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
