"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmButton } from "@/components/ui/dialog";
import { Select } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { PortalAccess } from "@/lib/api/types";

export function PortalAccessControls({ customerId, access, emails, canManage }: { customerId: string; access: PortalAccess; emails: string[]; canManage: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState(access.email ?? emails[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!canManage) return null;
  if (!emails.length) return <p className="text-sm text-muted">Add an email address to give this customer portal access.</p>;

  return (
    <div className="space-y-3">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {message ? <Alert tone="success">{message}</Alert> : null}
      <div className="flex flex-wrap items-center gap-2">
        {emails.length > 1 ? (
          <Select aria-label="Email for the portal" value={email} onChange={(e) => setEmail(e.target.value)} className="max-w-60">
            {emails.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </Select>
        ) : null}
        <Button
          size="sm"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            setMessage(null);
            try {
              await api("POST", `/customers/${customerId}/portal/invite`, { email });
              setMessage(`Sign-in link sent to ${email}.`);
              router.refresh();
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {access.enabled ? "Send a new sign-in link" : "Give portal access"}
        </Button>
        {access.enabled ? (
          <ConfirmButton
            trigger={<Button size="sm" variant="ghost">Remove access</Button>}
            title="Remove portal access?"
            description="The customer is signed out and can no longer sign in to the portal. Their records are not changed."
            confirmLabel="Remove access"
            destructive
            onConfirm={async () => {
              await api("POST", `/customers/${customerId}/portal/disable`).catch((e) => {
                throw new Error(errorMessage(e));
              });
              router.refresh();
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
