"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { Part, StockLevelRow, StockLocation, StockOperation } from "@/lib/api/types";
import { newIdempotencyKey } from "@/lib/invoice";
import { WHOLE_UNITS, qty } from "@/lib/inventory";

const QTY_RE = /^-?\d{1,10}(\.\d{1,2})?$/;

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function quantityError(value: string, part: Part, { allowNegative = false, allowZero = true } = {}): string | null {
  if (!value) return null;
  if (!QTY_RE.test(value) || (!allowNegative && value.startsWith("-"))) return "Enter a number with up to 2 decimals.";
  if (!allowZero && Number(value) === 0) return "Enter a quantity other than 0.";
  if (WHOLE_UNITS.includes(part.unit) && !Number.isInteger(Number(value))) return `${part.sku} is counted in whole units.`;
  return null;
}

/** Stocktake count or direct correction at one location. Reason is mandatory. */
export function AdjustButton({ part, level }: { part: Part; level: StockLevelRow }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [mode, setMode] = useState<"counted" | "change">("counted");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSubmit();
  const invalid = quantityError(value, part, { allowNegative: mode === "change", allowZero: mode === "counted" });
  const delta = value && !invalid ? (mode === "counted" ? Number(value) - Number(level.on_hand) : Number(value)) : null;
  const valid = Boolean(value) && !invalid && reason.trim().length >= 3;

  return (
    <>
      <Button size="sm" onClick={() => (setValue(""), setReason(""), setOpen(true))}>
        Count / adjust
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Adjust ${part.sku} at ${level.location.name}`} description={`On hand ${qty(level.on_hand)}, reserved for jobs ${qty(level.reserved)}.`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api<StockOperation>(
                "POST",
                "/inventory/adjustments",
                { location_id: level.location.id, reason: reason.trim(), lines: [{ part_id: part.id, [mode]: value }] },
                { idempotencyKey: key },
              );
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <fieldset className="flex gap-4 text-sm">
            <legend className="sr-only">Type of adjustment</legend>
            <label className="flex items-center gap-2">
              <input type="radio" name="mode" checked={mode === "counted"} onChange={() => (setMode("counted"), setValue(""))} />
              Counted quantity
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="mode" checked={mode === "change"} onChange={() => (setMode("change"), setValue(""))} />
              Add or remove
            </label>
          </fieldset>
          <Field
            label={mode === "counted" ? "Quantity counted" : "Change (use - to remove)"}
            required
            error={invalid ?? undefined}
            hint={delta !== null ? `Change: ${delta > 0 ? "+" : ""}${qty(String(delta))}, new on hand ${qty(String(Number(level.on_hand) + delta))}` : undefined}
          >
            {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={value} onChange={(e) => setValue(e.target.value.trim())} />}
          </Field>
          <Field label="Reason" required hint="For example: stocktake, damaged, opening stock.">
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Record adjustment
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function TransferButton({ part, level, locations }: { part: Part; level: StockLevelRow; locations: StockLocation[] }) {
  const router = useRouter();
  const targets = locations.filter((l) => l.id !== level.location.id && !l.archived_at);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [to, setTo] = useState(targets[0]?.id ?? "");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSubmit();
  const invalid = quantityError(value, part, { allowZero: false });
  const over = value && !invalid && Number(value) > Number(level.available) ? `Only ${qty(level.available)} available.` : null;
  const valid = Boolean(value) && !invalid && !over && Boolean(to);

  if (!targets.length || Number(level.available) <= 0) return null;
  return (
    <>
      <Button size="sm" onClick={() => (setValue(""), setOpen(true))}>
        Transfer
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Transfer ${part.sku} from ${level.location.name}`} description={`${qty(level.available)} available (stock reserved for jobs cannot be moved).`}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api<StockOperation>(
                "POST",
                "/inventory/transfers",
                { from_location_id: level.location.id, to_location_id: to, reason: reason.trim() || null, lines: [{ part_id: part.id, quantity: value }] },
                { idempotencyKey: key },
              );
              setKey(newIdempotencyKey());
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label="To" required>
              {(p) => (
                <Select {...p} value={to} onChange={(e) => setTo(e.target.value)}>
                  {targets.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.branch.name} · {l.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Quantity" required error={invalid ?? over ?? undefined}>
              {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={value} onChange={(e) => setValue(e.target.value.trim())} />}
            </Field>
          </div>
          <Field label="Note">{(p) => <Input {...p} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
              Transfer
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function MinLevelButton({ part, level }: { part: Part; level: StockLevelRow }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(level.min_quantity ? qty(level.min_quantity) : "");
  const { busy, error, run } = useSubmit();
  const invalid = quantityError(value, part);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Minimum
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Minimum for ${part.sku} at ${level.location.name}`} description="The part shows as low stock when the available quantity is at or below this. Leave empty for no alert.">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api("PUT", `/inventory/parts/${part.id}/levels/${level.location.id}`, { min_quantity: value || null });
              setOpen(false);
              router.refresh();
            });
          }}
        >
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Minimum quantity" error={invalid ?? undefined}>
            {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={value} onChange={(e) => setValue(e.target.value.trim())} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={Boolean(invalid)}>
              Save
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function ArchivePartButton({ part }: { part: Part }) {
  const router = useRouter();
  const archived = Boolean(part.archived_at);
  return (
    <ConfirmButton
      trigger={<Button>{archived ? "Restore" : "Archive"}</Button>}
      title={archived ? `Restore ${part.sku}?` : `Archive ${part.sku}?`}
      description={archived ? "The part can be stocked and used again." : "Archived parts stay in history but cannot be stocked or used. Only parts with no stock can be archived."}
      confirmLabel={archived ? "Restore" : "Archive"}
      destructive={!archived}
      onConfirm={async () => {
        await api("POST", `/inventory/parts/${part.id}/${archived ? "restore" : "archive"}`).catch((e) => {
          throw new Error(errorMessage(e));
        });
        router.refresh();
      }}
    />
  );
}
