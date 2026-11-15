"use client";

import { Button } from "@/components/ui/button";

import { TaxRateDialog } from "../settings-forms";

export function AddTaxRateButton() {
  return (
    <TaxRateDialog
      trigger={(open) => (
        <Button size="sm" variant="primary" onClick={open}>
          Add tax rate
        </Button>
      )}
    />
  );
}
