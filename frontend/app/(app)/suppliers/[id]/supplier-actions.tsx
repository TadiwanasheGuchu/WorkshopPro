"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PartPicker } from "@/components/app/part-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { BranchSummary, PartListItem, PurchaseOrder, Supplier } from "@/lib/api/types";

const MONEY_RE = /^\d{1,12}(\.\d{1,2})?$/;

type SupplierPart = Supplier["parts"][number];

export function SupplierPartButton({ supplierId, existing }: { supplierId: string; existing?: SupplierPart }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [part, setPart] = useState<PartListItem | null>(existing ? ({ id: existing.part.id, sku: existing.sku, name: existing.part.name, unit: existing.unit } as PartListItem) : null);
  const [code, setCode] = useState(existing?.supplier_sku ?? "");
  const [cost, setCost] = useState(existing?.last_cost ?? "");
  const [lead, setLead] = useState(existing?.lead_time_days != null ? String(existing.lead_time_days) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const costError = cost && !MONEY_RE.test(cost) ? "Enter an amount with up to 2 decimals." : null;
  const leadError = lead && !/^\d{1,3}$/.test(lead) ? "Whole days only." : null;

  return (
    <>
      <Button size={existing ? "sm" : "md"} variant={existing ? "ghost" : "secondary"} onClick={() => setOpen(true)}>
        {existing ? "Edit" : "Add part code"}
      </Button>
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={existing ? `${existing.sku} from this supplier` : "Add part code"} description="The supplier's own code and price are used when you order this part from them.">
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!part) return;
            setBusy(true);
            setError(null);
            try {
              await api("PUT", `/suppliers/${supplierId}/parts/${part.id}`, {
                supplier_sku: code.trim() || null,
                last_cost: cost || null,
                lead_time_days: lead ? Number(lead) : null,
              });
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
          {existing ? null : (
            <div className="space-y-1">
              <span className="text-sm font-medium">Part</span>
              <PartPicker value={part} onChange={setPart} />
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Supplier's code">{(p) => <Input {...p} className="font-mono" maxLength={100} value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
            <Field label="Price (excl. tax)" error={costError ?? undefined}>
              {(p) => <Input {...p} inputMode="decimal" className="text-right font-mono" value={cost} onChange={(e) => setCost(e.target.value.trim())} />}
            </Field>
            <Field label="Lead time (days)" error={leadError ?? undefined}>
              {(p) => <Input {...p} inputMode="numeric" value={lead} onChange={(e) => setLead(e.target.value.trim())} />}
            </Field>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!part || Boolean(costError || leadError)}>
              Save
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function RemoveSupplierPartButton({ supplierId, part }: { supplierId: string; part: SupplierPart }) {
  const router = useRouter();
  return (
    <ConfirmButton
      trigger={<Button size="sm" variant="ghost">Remove</Button>}
      title={`Remove ${part.sku} from this supplier?`}
      description="Only the supplier's code and price are removed. Orders already placed are not affected."
      confirmLabel="Remove"
      destructive
      onConfirm={async () => {
        await api("DELETE", `/suppliers/${supplierId}/parts/${part.part.id}`).catch((e) => {
          throw new Error(errorMessage(e));
        });
        router.refresh();
      }}
    />
  );
}

export function NewOrderButton({ supplierId, branches }: { supplierId: string; branches: BranchSummary[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [branch, setBranch] = useState(branches[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(branchId: string) {
    setBusy(true);
    setError(null);
    try {
      const po = await api<PurchaseOrder>("POST", "/purchase-orders", { branch_id: branchId, supplier_id: supplierId, lines: [] });
      router.push(`/purchase-orders/${po.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="primary" loading={busy && !open} onClick={() => (branches.length > 1 ? setOpen(true) : void create(branch))}>
        New purchase order
      </Button>
      {error && !open ? <span className="text-xs text-status-danger">{error}</span> : null}
      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title="New purchase order" description="Which branch is the order for? Goods are received into that branch's stock.">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Branch" required>
            {(p) => (
              <Select {...p} value={branch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" loading={busy} onClick={() => void create(branch)}>
              Start order
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

export function ArchiveSupplierButton({ supplier }: { supplier: Supplier }) {
  const router = useRouter();
  const archived = Boolean(supplier.archived_at);
  return (
    <ConfirmButton
      trigger={<Button>{archived ? "Restore" : "Archive"}</Button>}
      title={archived ? `Restore ${supplier.name}?` : `Archive ${supplier.name}?`}
      description={archived ? "Orders can be placed with this supplier again." : "Archived suppliers keep their history but cannot receive new orders. Suppliers with open orders cannot be archived."}
      confirmLabel={archived ? "Restore" : "Archive"}
      destructive={!archived}
      onConfirm={async () => {
        await api("POST", `/suppliers/${supplier.id}/${archived ? "restore" : "archive"}`).catch((e) => {
          throw new Error(errorMessage(e));
        });
        router.refresh();
      }}
    />
  );
}
