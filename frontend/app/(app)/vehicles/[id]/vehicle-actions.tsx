"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { CustomerPicker, type PickedCustomer } from "@/components/app/customer-picker";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

export function TransferVehicleButton({ vehicleId, currentOwnerId }: { vehicleId: string; currentOwnerId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [owner, setOwner] = useState<PickedCustomer | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function transfer() {
    if (!owner) return;
    setBusy(true);
    setError(null);
    try {
      await api("POST", `/vehicles/${vehicleId}/transfer`, { customer_id: owner.id, note: note.trim() || null });
      setOpen(false);
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>Transfer owner</Button>
      <Dialog open={open} onOpenChange={setOpen} title="Transfer to another customer" description="The current ownership is closed and kept in the history.">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="New owner" required>
            {(p) => <CustomerPicker inputId={p.id} value={owner} onChange={setOwner} excludeId={currentOwnerId} />}
          </Field>
          <Field label="Note" hint="e.g. Sold privately, fleet reassignment.">
            {(p) => <Input {...p} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!owner} loading={busy} onClick={() => void transfer()}>
              Transfer
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

export function ArchiveVehicleButton({ vehicleId, archived }: { vehicleId: string; archived: boolean }) {
  const router = useRouter();
  const action = archived ? "restore" : "archive";
  return (
    <ConfirmButton
      trigger={<Button variant={archived ? "secondary" : "danger"}>{archived ? "Restore vehicle" : "Archive vehicle"}</Button>}
      title={archived ? "Restore this vehicle?" : "Archive this vehicle?"}
      description={
        archived
          ? "The vehicle becomes active again for new jobs."
          : "Use this when the vehicle is scrapped or no longer serviced. Its history is kept and the registration can be used by another vehicle."
      }
      confirmLabel={archived ? "Restore" : "Archive"}
      destructive={!archived}
      onConfirm={async () => {
        await api("POST", `/vehicles/${vehicleId}/${action}`);
        router.refresh();
      }}
    />
  );
}
