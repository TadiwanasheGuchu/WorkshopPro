"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import type { LineKind, QuoteItem, TaxRate } from "@/lib/api/types";
import { LINE_KIND } from "@/lib/quotation";

/** Editable document lines shared by quotation and invoice drafts. Totals and tax are
 * always calculated by the server when the draft is saved. */
export interface Line {
  key: number;
  kind: LineKind;
  description: string;
  part_number: string;
  quantity: string;
  unit_price: string;
  tax_rate_id: string;
}

let nextKey = 1;

export const toLine = (i: QuoteItem): Line => ({
  key: nextKey++,
  kind: i.kind,
  description: i.description,
  part_number: i.part_number ?? "",
  quantity: i.quantity,
  unit_price: i.unit_price,
  tax_rate_id: i.tax_rate_id ?? "",
});

const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

export const linesInvalid = (lines: Line[]) =>
  lines.some((l) => !l.description.trim() || !MONEY_RE.test(l.quantity) || Number(l.quantity) <= 0 || !MONEY_RE.test(l.unit_price));

export const linesPayload = (lines: Line[]) =>
  lines.map((l) => ({
    kind: l.kind,
    description: l.description.trim(),
    part_number: l.part_number.trim() || null,
    quantity: l.quantity,
    unit_price: l.unit_price,
    tax_rate_id: l.tax_rate_id || null,
  }));

export function LineItemsEditor({ lines, onChange, taxRates }: { lines: Line[]; onChange: (lines: Line[]) => void; taxRates: TaxRate[] }) {
  const activeRates = taxRates.filter((r) => r.is_active);
  const defaultRate = activeRates.find((r) => r.is_default)?.id ?? "";

  function update(key: number, patch: Partial<Line>) {
    onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  function add(kind: LineKind) {
    onChange([
      ...lines,
      { key: nextKey++, kind, description: "", part_number: "", quantity: kind === "labour" ? "1.0" : "1", unit_price: "", tax_rate_id: defaultRate },
    ]);
  }

  return (
      <div className="space-y-3">
        {lines.length === 0 ? <p className="text-sm text-muted">No lines yet. Add labour, parts or fees below.</p> : null}
        {lines.map((l, index) => (
          <div key={l.key} className="grid gap-2 rounded-control border border-border p-3 md:grid-cols-[7rem_1fr_6rem_7rem_9rem_auto] md:items-start md:border-0 md:p-0">
            <Select aria-label={`Line ${index + 1} type`} value={l.kind} onChange={(e) => update(l.key, { kind: e.target.value as LineKind })}>
              {Object.entries(LINE_KIND).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
            <div className="space-y-1">
              <Input aria-label={`Line ${index + 1} description`} placeholder="Description" value={l.description} maxLength={500} onChange={(e) => update(l.key, { description: e.target.value })} />
              {l.kind === "part" ? (
                <Input aria-label={`Line ${index + 1} part number`} placeholder="Part number" className="font-mono" value={l.part_number} onChange={(e) => update(l.key, { part_number: e.target.value })} />
              ) : null}
            </div>
            <Input
              aria-label={`Line ${index + 1} ${l.kind === "labour" ? "hours" : "quantity"}`}
              inputMode="decimal"
              className="text-right font-mono"
              placeholder={l.kind === "labour" ? "Hours" : "Qty"}
              value={l.quantity}
              onChange={(e) => update(l.key, { quantity: e.target.value })}
            />
            <Input
              aria-label={`Line ${index + 1} ${l.kind === "labour" ? "rate per hour" : "unit price"}`}
              inputMode="decimal"
              className="text-right font-mono"
              placeholder={l.kind === "labour" ? "Rate / h" : "Price"}
              value={l.unit_price}
              onChange={(e) => update(l.key, { unit_price: e.target.value })}
            />
            <Select aria-label={`Line ${index + 1} tax`} value={l.tax_rate_id} onChange={(e) => update(l.key, { tax_rate_id: e.target.value })}>
              <option value="">No tax</option>
              {activeRates.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.rate_percent}%)
                </option>
              ))}
            </Select>
            <Button variant="ghost" aria-label={`Remove line ${index + 1}`} onClick={() => onChange(lines.filter((x) => x.key !== l.key))}>
              <X className="size-4" aria-hidden />
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          {(Object.keys(LINE_KIND) as LineKind[]).map((k) => (
            <Button key={k} size="sm" onClick={() => add(k)}>
              <Plus className="size-4" aria-hidden /> {LINE_KIND[k]}
            </Button>
          ))}
        </div>
      </div>
  );
}
