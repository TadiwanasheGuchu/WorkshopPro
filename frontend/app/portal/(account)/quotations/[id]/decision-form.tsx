"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

export function DecisionForm({ id }: { id: string }) {
  const router = useRouter();
  const [accept, setAccept] = useState(false);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approved" | "rejected") {
    setBusy(decision);
    setError(null);
    try {
      await api("POST", `/portal/quotations/${id}/decision`, { decision, accept_terms: accept, comments: comments.trim() || null });
      router.refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Field label="Comments for the workshop">{(p) => <Textarea {...p} rows={2} maxLength={2000} value={comments} onChange={(e) => setComments(e.target.value)} />}</Field>
      <Checkbox label="I accept this quotation, its total and its terms" checked={accept} onChange={(e) => setAccept(e.target.checked)} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" loading={busy === "approved"} disabled={!accept || busy !== null} onClick={() => void decide("approved")}>
          Approve quotation
        </Button>
        <Button loading={busy === "rejected"} disabled={busy !== null} onClick={() => void decide("rejected")}>
          Decline
        </Button>
      </div>
      <p className="text-xs text-muted">Your decision is recorded with this exact version and total.</p>
    </div>
  );
}
