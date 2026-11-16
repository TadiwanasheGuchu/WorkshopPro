"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { BranchSummary, StockLocation } from "@/lib/api/types";

function NameDialog({
  title,
  open,
  setOpen,
  initial,
  branches,
  submitLabel,
  onSave,
}: {
  title: string;
  open: boolean;
  setOpen: (o: boolean) => void;
  initial: string;
  branches?: BranchSummary[];
  submitLabel: string;
  onSave: (name: string, branchId: string) => Promise<void>;
}) {
  const [name, setName] = useState(initial);
  const [branchId, setBranchId] = useState(branches?.[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)} title={title}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await onSave(name.trim(), branchId);
            setOpen(false);
          } catch (err) {
            setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {error ? <Alert tone="error">{error}</Alert> : null}
        {branches && branches.length > 1 ? (
          <Field label="Branch" required>
            {(p) => (
              <Select {...p} value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ) : null}
        <Field label="Name" required hint="For example: Shelf B, Oil store, Service van.">
          {(p) => <Input {...p} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!name.trim()}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function AddLocationButton({ branches }: { branches: BranchSummary[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Add location
      </Button>
      {open ? (
        <NameDialog
          title="Add stock location"
          open={open}
          setOpen={setOpen}
          initial=""
          branches={branches}
          submitLabel="Add location"
          onSave={async (name, branchId) => {
            await api("POST", "/inventory/locations", { branch_id: branchId, name });
            router.refresh();
          }}
        />
      ) : null}
    </>
  );
}

export function LocationActions({ location }: { location: StockLocation }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const archived = Boolean(location.archived_at);
  return (
    <span className="flex gap-2">
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        Rename
      </Button>
      {open ? (
        <NameDialog
          title={`Rename ${location.name}`}
          open={open}
          setOpen={setOpen}
          initial={location.name}
          submitLabel="Save"
          onSave={async (name) => {
            await api("PATCH", `/inventory/locations/${location.id}`, { name });
            router.refresh();
          }}
        />
      ) : null}
      {!location.is_default ? (
        <ConfirmButton
          trigger={<Button size="sm">{archived ? "Restore" : "Archive"}</Button>}
          title={archived ? `Restore ${location.name}?` : `Archive ${location.name}?`}
          description={archived ? "Stock can be held here again." : "Only empty locations can be archived. Its movement history is kept."}
          confirmLabel={archived ? "Restore" : "Archive"}
          destructive={!archived}
          onConfirm={async () => {
            await api("POST", `/inventory/locations/${location.id}/${archived ? "restore" : "archive"}`).catch((e) => {
              throw new Error(errorMessage(e));
            });
            router.refresh();
          }}
        />
      ) : null}
    </span>
  );
}
