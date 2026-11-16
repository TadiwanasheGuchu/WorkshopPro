"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PartPicker } from "@/components/app/part-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Panel } from "@/components/ui/page";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { JobParts, PartListItem } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { newIdempotencyKey } from "@/lib/invoice";
import { WHOLE_UNITS, qty } from "@/lib/inventory";

type Mode = "reserve" | "issue" | "return";

const TITLES: Record<Mode, string> = { reserve: "Reserve parts", issue: "Issue parts", return: "Return parts to stock" };
const PATHS: Record<Mode, string> = { reserve: "reservations", issue: "issues", return: "returns" };

function PartsDialog({ mode, jobId, parts, onClose, initialPart }: { mode: Mode; jobId: string; parts: JobParts; onClose: () => void; initialPart?: PartListItem | null }) {
  const router = useRouter();
  const [key] = useState(newIdempotencyKey);
  const [part, setPart] = useState<PartListItem | null>(initialPart ?? null);
  const [location, setLocation] = useState(parts.locations[0]?.id ?? "");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const qtyError =
    !/^\d{1,10}(\.\d{1,2})?$/.test(quantity) || Number(quantity) <= 0
      ? "Enter a quantity above 0."
      : part && WHOLE_UNITS.includes(part.unit) && !Number.isInteger(Number(quantity))
        ? `${part.sku} is counted in whole units.`
        : null;
  const valid = Boolean(part) && Boolean(location) && !qtyError && (mode !== "return" || reason.trim().length >= 3);

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && !busy && onClose()}
      title={TITLES[mode]}
      description={mode === "issue" ? "Issue parts when they are fitted. Stock reserved for this job is used first." : mode === "reserve" ? "Holds stock for this job so it is not used elsewhere." : undefined}
    >
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!part) return;
          setBusy(true);
          setError(null);
          try {
            await api(
              "POST",
              `/job-cards/${jobId}/parts/${PATHS[mode]}`,
              { location_id: location, ...(mode === "return" ? { reason: reason.trim() } : {}), lines: [{ part_id: part.id, quantity }] },
              { idempotencyKey: key },
            );
            onClose();
            router.refresh();
          } catch (err) {
            setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {error ? <Alert tone="error">{error}</Alert> : null}
        {mode === "return" && initialPart ? null : (
          <div className="space-y-1">
            <span className="text-sm font-medium">Part</span>
            <PartPicker value={part} onChange={setPart} />
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
          <Field label={mode === "return" ? "Return to" : "From"} required>
            {(p) => (
              <Select {...p} value={location} onChange={(e) => setLocation(e.target.value)}>
                {parts.locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Quantity" required error={quantity ? (qtyError ?? undefined) : undefined}>
            {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={quantity} onChange={(e) => setQuantity(e.target.value.trim())} />}
          </Field>
        </div>
        {mode === "return" ? (
          <Field label="Reason" required>
            {(p) => <Textarea {...p} rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!valid}>
            {mode === "reserve" ? "Reserve" : mode === "issue" ? "Issue" : "Return"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ReleaseButton({ jobId, reservationId, label }: { jobId: string; reservationId: string; label: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Release
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={`Release ${label}?`} description="The stock becomes available again.">
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await api("POST", `/job-cards/${jobId}/parts/reservations/${reservationId}/release`, { reason: reason.trim() });
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
            {(p) => <Input {...p} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={reason.trim().length < 3}>
              Release
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function PartsPanel({ jobId, parts }: { jobId: string; parts: JobParts }) {
  const [dialog, setDialog] = useState<{ mode: Mode; part?: PartListItem | null } | null>(null);
  const caps = parts.capabilities;
  const open = parts.reservations.filter((r) => r.status === "open");
  const c = parts.currency_code;

  return (
    <Panel
      title="Parts"
      flush
      actions={
        caps.reserve || caps.issue ? (
          <span className="flex gap-2">
            {caps.reserve ? (
              <Button size="sm" onClick={() => setDialog({ mode: "reserve" })}>
                Reserve
              </Button>
            ) : null}
            {caps.issue ? (
              <Button size="sm" onClick={() => setDialog({ mode: "issue" })}>
                Issue parts
              </Button>
            ) : null}
          </span>
        ) : null
      }
    >
      {!parts.authorised && caps.release ? (
        <p className="border-b border-border px-4 py-2 text-sm text-muted">Parts can be reserved and issued once the customer approves the quotation, or an approval exception is recorded.</p>
      ) : null}

      {open.length ? (
        <section aria-label="Reserved" className="border-b border-border">
          <h3 className="px-4 pt-3 text-xs font-medium text-muted">Reserved</h3>
          <ul className="divide-y divide-border">
            {open.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                <span>
                  <span className="font-mono">{r.sku}</span> {r.part.name}
                  <span className="block text-xs text-muted">{r.location.name}</span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="font-mono tabular-nums">{qty(r.outstanding)}</span>
                  {caps.release ? <ReleaseButton jobId={jobId} reservationId={r.id} label={`${qty(r.outstanding)} ${r.sku}`} /> : null}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-label="Fitted">
        <h3 className="px-4 pt-3 text-xs font-medium text-muted">Fitted to this job</h3>
        {parts.used.length === 0 ? (
          <p className="px-4 py-2 text-sm text-muted">No parts issued yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {parts.used.map((u) => (
              <li key={u.part.id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                <span>
                  <span className="font-mono">{u.sku}</span> {u.part.name}
                  <span className="block text-xs text-muted">at {formatMoney(u.selling_price, c)} each, current price</span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-right font-mono tabular-nums">
                    {qty(u.issued)}
                    <span className="block text-xs text-muted">{formatMoney(u.value, c)}</span>
                  </span>
                  {caps.return_parts ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setDialog({
                          mode: "return",
                          part: { id: u.part.id, sku: u.sku, name: u.part.name, unit: u.unit } as PartListItem,
                        })
                      }
                    >
                      Return
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {dialog ? <PartsDialog mode={dialog.mode} jobId={jobId} parts={parts} initialPart={dialog.part} onClose={() => setDialog(null)} /> : null}
    </Panel>
  );
}
