"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { Part, PartCategory, PartUnit, TaxRate } from "@/lib/api/types";
import { applyApiError } from "@/lib/forms";
import { UNIT_LABEL } from "@/lib/inventory";

const money = z
  .string()
  .trim()
  .regex(/^\d{1,12}(\.\d{1,2})?$/, "Enter an amount with up to 2 decimals.");

const schema = z.object({
  sku: z
    .string()
    .trim()
    .min(1, "Enter the SKU.")
    .max(50)
    .regex(/^[A-Za-z0-9][A-Za-z0-9 ._/-]*$/, "Letters, numbers, spaces and . _ / - only."),
  name: z.string().trim().min(1, "Enter the name.").max(200),
  description: z.string().max(2000),
  category_id: z.string(),
  new_category: z.string().max(100),
  unit: z.enum(["each", "pair", "set", "box", "litre", "kg", "metre"]),
  manufacturer: z.string().max(100),
  manufacturer_part_number: z.string().max(100),
  cost_price: money,
  selling_price: money,
  tax_rate_id: z.string(),
});
type Values = z.infer<typeof schema>;

const blank = (v: string) => (v.trim() ? v.trim() : null);

export function PartForm({ part, categories, taxRates }: { part?: Part; categories: PartCategory[]; taxRates: TaxRate[] }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const activeRates = taxRates.filter((r) => r.is_active);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      sku: part?.sku ?? "",
      name: part?.name ?? "",
      description: part?.description ?? "",
      category_id: part?.category?.id ?? "",
      new_category: "",
      unit: part?.unit ?? "each",
      manufacturer: part?.manufacturer ?? "",
      manufacturer_part_number: part?.manufacturer_part_number ?? "",
      cost_price: part?.cost_price ?? "0.00",
      selling_price: part?.selling_price ?? "0.00",
      tax_rate_id: part ? (part.tax_rate?.id ?? "") : (activeRates.find((r) => r.is_default)?.id ?? ""),
    },
  });
  const { errors, isSubmitting } = form.formState;

  async function onSubmit(v: Values) {
    setError(null);
    try {
      let categoryId = v.category_id || null;
      if (v.new_category.trim()) {
        const created = await api<PartCategory>("POST", "/inventory/categories", { name: v.new_category.trim() });
        categoryId = created.id;
      }
      const body = {
        sku: v.sku.trim(),
        name: v.name.trim(),
        description: blank(v.description),
        category_id: categoryId,
        unit: v.unit as PartUnit,
        manufacturer: blank(v.manufacturer),
        manufacturer_part_number: blank(v.manufacturer_part_number),
        cost_price: v.cost_price.trim(),
        selling_price: v.selling_price.trim(),
        tax_rate_id: v.tax_rate_id || null,
      };
      const saved = part ? await api<Part>("PATCH", `/inventory/parts/${part.id}`, body) : await api<Part>("POST", "/inventory/parts", body);
      router.push(`/inventory/parts/${saved.id}`);
      router.refresh();
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5" noValidate>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-[12rem_1fr]">
        <Field label="SKU" required error={errors.sku?.message} hint="Your own stock code.">
          {(p) => <Input {...p} className="font-mono" autoCapitalize="characters" {...form.register("sku")} />}
        </Field>
        <Field label="Name" required error={errors.name?.message}>
          {(p) => <Input {...p} {...form.register("name")} />}
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Category">
          {(p) => (
            <Select {...p} {...form.register("category_id")}>
              <option value="">None</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Or new category" hint="Created when you save." error={errors.new_category?.message}>
          {(p) => <Input {...p} {...form.register("new_category")} />}
        </Field>
        <Field label="Unit" required>
          {(p) => (
            <Select {...p} {...form.register("unit")}>
              {Object.entries(UNIT_LABEL).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Manufacturer">{(p) => <Input {...p} {...form.register("manufacturer")} />}</Field>
        <Field label="Manufacturer part number">{(p) => <Input {...p} className="font-mono" {...form.register("manufacturer_part_number")} />}</Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Cost price" required error={errors.cost_price?.message} hint="What you pay, excl. tax.">
          {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" {...form.register("cost_price")} />}
        </Field>
        <Field label="Selling price" required error={errors.selling_price?.message}>
          {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" {...form.register("selling_price")} />}
        </Field>
        <Field label="Tax">
          {(p) => (
            <Select {...p} {...form.register("tax_rate_id")}>
              <option value="">No tax</option>
              {activeRates.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.rate_percent}%)
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Field label="Description" error={errors.description?.message}>
        {(p) => <Textarea {...p} rows={3} {...form.register("description")} />}
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" loading={isSubmitting}>
          {part ? "Save part" : "Add part"}
        </Button>
        <Button type="button" onClick={() => router.back()}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
