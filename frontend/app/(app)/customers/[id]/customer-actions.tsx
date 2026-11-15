"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { applyApiError } from "@/lib/forms";
import { CONSENT_CHANNEL, CONSENT_METHOD } from "@/lib/labels";

const schema = z.object({
  channel: z.enum(["whatsapp", "sms", "email", "marketing"]),
  status: z.enum(["granted", "withdrawn"]),
  method: z.enum(["verbal", "written", "signed_form", "customer_portal", "other"]),
  evidence: z.string().max(500),
});
type Values = z.infer<typeof schema>;

export function RecordConsentButton({ customerId }: { customerId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { channel: "whatsapp", status: "granted", method: "verbal", evidence: "" },
  });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      await api("POST", `/customers/${customerId}/consents`, { ...values, evidence: values.evidence.trim() || null });
      setOpen(false);
      form.reset();
      router.refresh();
    } catch (e) {
      setError(applyApiError(form, e));
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Record consent
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Record communication consent"
        description="Records are kept as evidence and never edited. Record a withdrawal to change consent."
      >
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Channel">
            {(p) => (
              <Select {...p} {...form.register("channel")}>
                {Object.entries(CONSENT_CHANNEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Consent">
            {(p) => (
              <Select {...p} {...form.register("status")}>
                <option value="granted">Customer agrees</option>
                <option value="withdrawn">Customer withdraws / declines</option>
              </Select>
            )}
          </Field>
          <Field label="How it was given">
            {(p) => (
              <Select {...p} {...form.register("method")}>
                {Object.entries(CONSENT_METHOD).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Evidence" hint="e.g. Signed intake form #231, or who heard the verbal consent." error={form.formState.errors.evidence?.message}>
            {(p) => <Input {...p} {...form.register("evidence")} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={form.formState.isSubmitting}>
              Record
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

export function ArchiveCustomerButton({ customerId, archived, name }: { customerId: string; archived: boolean; name: string }) {
  const router = useRouter();
  return archived ? (
    <ConfirmButton
      trigger={<Button>Restore customer</Button>}
      title={`Restore ${name}?`}
      description="The customer appears in searches again and can receive new vehicles and jobs."
      confirmLabel="Restore"
      onConfirm={async () => {
        await api("POST", `/customers/${customerId}/restore`);
        router.refresh();
      }}
    />
  ) : (
    <ConfirmButton
      trigger={<Button variant="danger">Archive customer</Button>}
      title={`Archive ${name}?`}
      description="Archived customers are hidden from searches. Their history is kept and you can restore them. Vehicles must be transferred or archived first."
      confirmLabel="Archive"
      destructive
      onConfirm={async () => {
        await api("POST", `/customers/${customerId}/archive`);
        router.refresh();
      }}
    />
  );
}
