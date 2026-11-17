"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { NotificationTemplate } from "@/lib/api/types";

export function TemplateForm({ template, canEdit }: { template: NotificationTemplate; canEdit: boolean }) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(template.is_enabled);
  const [subject, setSubject] = useState(template.email_subject);
  const [body, setBody] = useState(template.email_body);
  const [waName, setWaName] = useState(template.whatsapp_template_name ?? "");
  const [waLang, setWaLang] = useState(template.whatsapp_language);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const waInvalid = waName && !/^[a-z0-9_]+$/.test(waName);

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        setSaved(false);
        try {
          await api("PUT", `/notification-templates/${template.event}`, {
            is_enabled: enabled,
            email_subject: subject,
            email_body: body,
            whatsapp_template_name: waName.trim() || null,
            whatsapp_language: waLang.trim() || "en",
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
      <Checkbox label="Send this notification" checked={enabled} disabled={!canEdit} onChange={(e) => setEnabled(e.target.checked)} />
      <Field label="Email subject" required>
        {(p) => <Input {...p} maxLength={200} disabled={!canEdit} value={subject} onChange={(e) => setSubject(e.target.value)} />}
      </Field>
      <Field label="Message" required hint="Used for email. Placeholders are listed below.">
        {(p) => <Textarea {...p} rows={7} maxLength={4000} disabled={!canEdit} value={body} onChange={(e) => setBody(e.target.value)} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
        <Field label="WhatsApp template name" hint="The name of the template approved by Meta. Leave empty to send by email only." error={waInvalid ? "Lowercase letters, digits and underscores only." : undefined}>
          {(p) => <Input {...p} className="font-mono" maxLength={100} disabled={!canEdit} value={waName} onChange={(e) => setWaName(e.target.value)} />}
        </Field>
        <Field label="Language">{(p) => <Input {...p} className="font-mono" maxLength={10} disabled={!canEdit} value={waLang} onChange={(e) => setWaLang(e.target.value)} />}</Field>
      </div>
      <div className="rounded-control border border-border p-3 text-sm">
        <p className="font-medium">Placeholders</p>
        <dl className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-2">
          {Object.entries(template.placeholders).map(([key, label]) => (
            <div key={key} className="flex gap-2">
              <dt className="font-mono text-xs">{`{${key}}`}</dt>
              <dd className="text-xs text-muted">{label}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-xs text-muted">
          WhatsApp template body parameters, in order: {template.whatsapp_params.map((p, i) => `{{${i + 1}}} = ${p}`).join(", ")}.
        </p>
      </div>
      {canEdit ? (
        <Button type="submit" variant="primary" loading={busy} disabled={Boolean(waInvalid)}>
          Save
        </Button>
      ) : null}
    </form>
  );
}
