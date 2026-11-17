"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { PortalMe } from "@/lib/api/types";

export function ProfileForm({ me }: { me: PortalMe }) {
  const router = useRouter();
  const [phone, setPhone] = useState(me.phone ?? "");
  const [method, setMethod] = useState(me.preferred_contact_method);
  const [whatsapp, setWhatsapp] = useState(me.whatsapp_consent);
  const [email, setEmail] = useState(me.email_consent);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        setSaved(false);
        try {
          await api("PATCH", "/portal/me", {
            ...(phone.trim() && phone.trim() !== (me.phone ?? "") ? { phone: phone.trim() } : {}),
            preferred_contact_method: method,
            whatsapp_consent: whatsapp,
            email_consent: email,
          });
          setSaved(true);
          router.refresh();
        } catch (err) {
          setError(errorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {saved ? <Alert tone="success">Saved.</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Mobile number">{(p) => <Input {...p} type="tel" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />}</Field>
        <Field label="Preferred contact method">
          {(p) => (
            <Select {...p} value={method} onChange={(e) => setMethod(e.target.value as PortalMe["preferred_contact_method"])}>
              <option value="whatsapp">WhatsApp</option>
              <option value="email">Email</option>
              <option value="phone">Phone call</option>
              <option value="sms">SMS</option>
            </Select>
          )}
        </Field>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Messages about your vehicle</legend>
        <Checkbox label="Send me updates by WhatsApp" description="Vehicle received, quotation ready, ready for collection and invoices." checked={whatsapp} onChange={(e) => setWhatsapp(e.target.checked)} />
        <Checkbox label="Send me updates by email" checked={email} onChange={(e) => setEmail(e.target.checked)} />
      </fieldset>
      <Button type="submit" variant="primary" loading={busy}>
        Save
      </Button>
    </form>
  );
}
