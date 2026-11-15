"use client";

import { X } from "lucide-react";
import { AlertDialog, Dialog as RadixDialog } from "radix-ui";
import { useState, type ReactNode } from "react";

import { Button } from "./button";

const overlay = "fixed inset-0 z-40 bg-slate-deep/40";
const panel =
  "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 " +
  "rounded-panel border border-border bg-surface p-5 shadow-lg focus:outline-none";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={overlay} />
        <RadixDialog.Content className={panel}>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <RadixDialog.Title className="text-base font-semibold">{title}</RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className="mt-1 text-sm text-muted">
                  {description}
                </RadixDialog.Description>
              ) : (
                <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
              )}
            </div>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close">
                <X className="size-4" aria-hidden />
              </Button>
            </RadixDialog.Close>
          </div>
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/**
 * Confirmation for destructive or significant actions. `onConfirm` may be async;
 * the dialog stays open and shows the error if it throws.
 */
export function ConfirmButton({
  trigger,
  title,
  description,
  confirmLabel,
  destructive = false,
  onConfirm,
}: {
  trigger: ReactNode;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AlertDialog.Root open={open} onOpenChange={(o) => !busy && setOpen(o)}>
      <AlertDialog.Trigger asChild>{trigger}</AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className={overlay} />
        <AlertDialog.Content className={panel}>
          <AlertDialog.Title className="text-base font-semibold">{title}</AlertDialog.Title>
          <AlertDialog.Description className="mt-1.5 text-sm text-muted">
            {description}
          </AlertDialog.Description>
          {error ? (
            <p role="alert" className="mt-3 text-sm font-medium text-status-danger">
              {error}
            </p>
          ) : null}
          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AlertDialog.Cancel asChild>
              <Button disabled={busy}>Cancel</Button>
            </AlertDialog.Cancel>
            <Button
              variant={destructive ? "danger" : "primary"}
              loading={busy}
              onClick={(e) => {
                e.preventDefault();
                void confirm();
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
