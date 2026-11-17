"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

export function RequestLinkForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (sent) {
    return (
      <Alert tone="success" className="mt-4" title="Check your email">
        If {email} has access to the portal, a sign-in link is on its way. It works once and expires in 15 minutes.
      </Alert>
    );
  }
  return (
    <form
      className="mt-4 space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api("POST", "/portal/auth/request-link", { email: email.trim() });
          setSent(true);
        } catch (err) {
          setError(errorMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Field label="Email" required>
        {(p) => <Input {...p} type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
      </Field>
      <Button type="submit" variant="primary" loading={busy} disabled={!email.includes("@")} className="w-full">
        Email me a sign-in link
      </Button>
    </form>
  );
}
