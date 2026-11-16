"use client";

import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PartPicker } from "@/components/app/part-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { PartListItem, PartUnit, PurchaseOrder } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { newIdempotencyKey } from "@/lib/invoice";
import { WHOLE_UNITS, qty } from "@/lib/inventory";

const QTY_RE = /^\d{1,10}(\.\d{1,2})?$/;
const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

function qtyProblem(value: string, unit: PartUnit, { allowZero = false } = {}): string | null {
  if (!QTY_RE.test(value)) return "Enter a number.";
  if (!allowZero && Number(value) <= 0) return "Above 0.";
  if (WHOLE_UNITS.includes(unit) && !Number.isInteger(Number(value))) return "Whole units only.";
  return null;
}

interface DraftLine {
  key: number;
  part: { id: string; sku: string; name: string; unit: PartUnit };
  quantity: string;
  unit_cost: string;
}

let nextKey = 1;

export function DraftEditor({ po }: { po: PurchaseOrder }) {
  const router = useRouter();
  const [lines, setLines] = useState<DraftLine[]>(
    po.lines.map((l) => ({ key: nextKey++, part: { id: l.part.id, sku: l.sku, name: l.part.name, unit: l.unit }, quantity: qty(l.quantity_ordered), unit_cost: l.unit_cost })),
  );
  const [expected, setExpected] = useState(po.expected_date ?? "");
  const [notes, setNotes] = useState(po.notes ?? "");
  const [picker, setPicker] = useState<PartListItem | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invalid = lines.some((l) => qtyProblem(l.quantity, l.part.unit) || (l.unit_cost && !MONEY_RE.test(l.unit_cost)));

  function update(key: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
    setDirty(true);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("PUT", `/purchase-orders/${po.id}/draft`, {
        version: po.version,
        expected_date: expected || null,
        notes: notes.trim() || null,
        lines: lines.map((l) => ({ part_id: l.part.id, quantity: l.quantity, unit_cost: l.unit_cost || null })),
      });
      setDirty(false);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {lines.length === 0 ? <p className="text-sm text-muted">No lines yet. Search for a part below to add it.</p> : null}
      {lines.map((l, i) => (
        <div key={l.key} className="grid gap-2 rounded-control border border-border p-3 sm:grid-cols-[1fr_7rem_9rem_auto] sm:items-start sm:border-0 sm:p-0">
          <div className="text-sm">
            <span className="font-mono">{l.part.sku}</span> {l.part.name}
          </div>
          <Field label="Qty" error={l.quantity ? (qtyProblem(l.quantity, l.part.unit) ?? undefined) : undefined}>
            {(p) => <Input {...p} aria-label={`Line ${i + 1} quantity`} inputMode="decimal" className="text-right font-mono" value={l.quantity} onChange={(e) => update(l.key, { quantity: e.target.value.trim() })} />}
          </Field>
          <Field label="Unit cost" hint={l.unit_cost ? undefined : "Supplier's last price"}>
            {(p) => <Input {...p} aria-label={`Line ${i + 1} unit cost`} inputMode="decimal" className="text-right font-mono" value={l.unit_cost} onChange={(e) => update(l.key, { unit_cost: e.target.value.trim() })} />}
          </Field>
          <Button variant="ghost" aria-label={`Remove line ${i + 1}`} className="sm:mt-6" onClick={() => (setLines((p) => p.filter((x) => x.key !== l.key)), setDirty(true))}>
            <X className="size-4" aria-hidden />
          </Button>
        </div>
      ))}
      <div className="max-w-md space-y-1">
        <span className="text-sm font-medium">Add a part</span>
        <PartPicker
          value={picker}
          onChange={(p) => {
            if (!p) return setPicker(null);
            if (!lines.some((l) => l.part.id === p.id)) {
              setLines((prev) => [...prev, { key: nextKey++, part: { id: p.id, sku: p.sku, name: p.name, unit: p.unit }, quantity: "1", unit_cost: "" }]);
              setDirty(true);
            }
            setPicker(null);
          }}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Required by">{(p) => <Input {...p} type="date" value={expected} onChange={(e) => (setExpected(e.target.value), setDirty(true))} />}</Field>
      </div>
      <Field label="Notes for the supplier">{(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => (setNotes(e.target.value), setDirty(true))} />}</Field>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={busy} disabled={!dirty || invalid} onClick={() => void save()}>
          Save draft
        </Button>
        {dirty ? <span className="text-sm text-muted">Unsaved changes. Totals update when you save.</span> : null}
      </div>
    </div>
  );
}

export function ApproveButton({ po }: { po: PurchaseOrder }) {
  const router = useRouter();
  return (
    <ConfirmButton
      trigger={<Button variant="primary">Approve order</Button>}
      title={`Approve ${po.po_number}?`}
      description={`${po.supplier.name}, ${formatMoney(po.total, po.currency_code)} excl. tax. After approval the order can be sent to the supplier and goods received against it.`}
      confirmLabel="Approve"
      onConfirm={async () => {
        await api("POST", `/purchase-orders/${po.id}/approve`, { version: po.version }).catch((e) => {
          throw new Error(errorMessage(e));
        });
        router.refresh();
      }}
    />
  );
}

export function EndOrderButton({ po, mode }: { po: PurchaseOrder; mode: "cancel" | "close" }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <Button onClick={() => setOpen(true)}>{mode === "cancel" ? "Cancel order" : "Close short"}</Button>
      <Dialog
        open={open}
        onOpenChange={(o) => !busy && setOpen(o)}
        title={mode === "cancel" ? `Cancel ${po.po_number}?` : `Close ${po.po_number} short?`}
        description={mode === "cancel" ? "Nothing has been received. The order is kept for the record." : "What was received stays in stock. The remaining quantities are no longer expected."}
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("POST", `/purchase-orders/${po.id}/${mode}`, { version: po.version, reason: reason.trim() });
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Back
            </Button>
            <Button type="submit" variant="danger" loading={busy} disabled={reason.trim().length < 3}>
              {mode === "cancel" ? "Cancel order" : "Close short"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

/** Record a delivery. Quantities default to what is still outstanding on each line. */
export function ReceiveButton({ po }: { po: PurchaseOrder }) {
  const router = useRouter();
  const outstanding = po.lines.filter((l) => Number(l.outstanding) > 0);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [location, setLocation] = useState(po.locations[0]?.id ?? "");
  const [delivery, setDelivery] = useState("");
  const [invoice, setInvoice] = useState("");
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const problems = outstanding.map((l) => {
    const v = amounts[l.id] ?? "";
    if (!v) return null;
    return qtyProblem(v, l.unit, { allowZero: true }) ?? (Number(v) > Number(l.outstanding) ? `At most ${qty(l.outstanding)}.` : null);
  });
  const chosen = outstanding.filter((l) => Number(amounts[l.id] || 0) > 0);
  const valid = chosen.length > 0 && problems.every((p) => !p) && Boolean(location);

  return (
    <>
      <Button
        variant="primary"
        onClick={() => {
          setAmounts(Object.fromEntries(outstanding.map((l) => [l.id, qty(l.outstanding)])));
          setNotes({});
          setOpen(true);
        }}
      >
        Receive delivery
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Receive against ${po.po_number}`} description="Enter what actually arrived. Partial deliveries are fine; the rest stays outstanding.">
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api(
                "POST",
                `/purchase-orders/${po.id}/receive`,
                {
                  location_id: location,
                  delivery_reference: delivery.trim() || null,
                  supplier_invoice_reference: invoice.trim() || null,
                  lines: chosen.map((l) => ({ po_line_id: l.id, quantity: amounts[l.id], discrepancy: notes[l.id]?.trim() || null })),
                },
                { idempotencyKey: key },
              );
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Into" required>
              {(p) => (
                <Select {...p} value={location} onChange={(e) => setLocation(e.target.value)}>
                  {po.locations.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Delivery note">{(p) => <Input {...p} maxLength={100} value={delivery} onChange={(e) => setDelivery(e.target.value)} />}</Field>
            <Field label="Supplier invoice">{(p) => <Input {...p} maxLength={100} value={invoice} onChange={(e) => setInvoice(e.target.value)} />}</Field>
          </div>
          <ul className="divide-y divide-border rounded-control border border-border">
            {outstanding.map((l, i) => (
              <li key={l.id} className="grid gap-2 p-3 sm:grid-cols-[1fr_7rem] sm:items-start">
                <div className="text-sm">
                  <span className="font-mono">{l.sku}</span> {l.part.name}
                  <span className="block text-xs text-muted">{qty(l.outstanding)} outstanding</span>
                  <Input aria-label={`${l.sku} discrepancy note`} placeholder="Note, e.g. box damaged" className="mt-2" maxLength={500} value={notes[l.id] ?? ""} onChange={(e) => setNotes((n) => ({ ...n, [l.id]: e.target.value }))} />
                </div>
                <Field label="Received" error={problems[i] ?? undefined}>
                  {(p) => <Input {...p} aria-label={`${l.sku} received`} inputMode="decimal" className="text-right font-mono" value={amounts[l.id] ?? ""} onChange={(e) => setAmounts((a) => ({ ...a, [l.id]: e.target.value.trim() }))} />}
                </Field>
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Record delivery
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function ReturnButton({ po }: { po: PurchaseOrder }) {
  const router = useRouter();
  const returnable = po.lines.filter((l) => Number(l.quantity_received) > Number(l.quantity_returned));
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [location, setLocation] = useState(po.locations[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const max = (l: (typeof returnable)[number]) => Number(l.quantity_received) - Number(l.quantity_returned);
  const problems = returnable.map((l) => {
    const v = amounts[l.id] ?? "";
    if (!v) return null;
    return qtyProblem(v, l.unit, { allowZero: true }) ?? (Number(v) > max(l) ? `At most ${qty(String(max(l)))}.` : null);
  });
  const chosen = returnable.filter((l) => Number(amounts[l.id] || 0) > 0);
  const valid = chosen.length > 0 && problems.every((p) => !p) && reason.trim().length >= 3;

  if (!returnable.length) return null;
  return (
    <>
      <Button onClick={() => (setAmounts({}), setOpen(true))}>Return to supplier</Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Return goods from ${po.po_number}`} description="Stock leaves the chosen location. Reserved stock cannot be returned.">
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api(
                "POST",
                `/purchase-orders/${po.id}/returns`,
                { location_id: location, reason: reason.trim(), reference: reference.trim() || null, lines: chosen.map((l) => ({ po_line_id: l.id, quantity: amounts[l.id] })) },
                { idempotencyKey: key },
              );
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            } catch (err) {
              setError(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="From" required>
              {(p) => (
                <Select {...p} value={location} onChange={(e) => setLocation(e.target.value)}>
                  {po.locations.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Return authorisation / reference">{(p) => <Input {...p} maxLength={100} value={reference} onChange={(e) => setReference(e.target.value)} />}</Field>
          </div>
          <ul className="divide-y divide-border rounded-control border border-border">
            {returnable.map((l, i) => (
              <li key={l.id} className="grid gap-2 p-3 sm:grid-cols-[1fr_7rem] sm:items-start">
                <div className="text-sm">
                  <span className="font-mono">{l.sku}</span> {l.part.name}
                  <span className="block text-xs text-muted">up to {qty(String(max(l)))}</span>
                </div>
                <Field label="Return" error={problems[i] ?? undefined}>
                  {(p) => <Input {...p} aria-label={`${l.sku} return`} inputMode="decimal" className="text-right font-mono" value={amounts[l.id] ?? ""} onChange={(e) => setAmounts((a) => ({ ...a, [l.id]: e.target.value.trim() }))} />}
                </Field>
              </li>
            ))}
          </ul>
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Record return
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
