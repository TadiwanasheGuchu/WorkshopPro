"use client";

import { Copy } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type Line, LineItemsEditor, linesInvalid, linesPayload, toLine } from "@/components/app/line-items-editor";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { Quotation, TaxRate } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { DECISION_METHOD } from "@/lib/quotation";


export function DraftEditor({ quote, taxRates }: { quote: Quotation; taxRates: TaxRate[] }) {
  const router = useRouter();
  const v = quote.current;
  const activeRates = taxRates.filter((r) => r.is_active);
  const [lines, setLines] = useState<Line[]>(v.items.map(toLine));
  const [validUntil, setValidUntil] = useState(v.valid_until ?? "");
  const [terms, setTerms] = useState(v.terms ?? "");
  const [notes, setNotes] = useState(v.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const invalid = linesInvalid(lines);

  async function save(): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await api("PUT", `/quotations/${quote.id}/draft`, {
        valid_until: validUntil || null,
        terms: terms.trim() || null,
        notes: notes.trim() || null,
        items: linesPayload(lines),
      });
      setDirty(false);
      router.refresh();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <Alert tone="error">{error}</Alert> : null}
      {activeRates.length === 0 ? (
        <Alert tone="info" title="No tax rates configured">
          Lines will be saved without tax. Add rates under Settings → Tax rates.
        </Alert>
      ) : null}

      <LineItemsEditor lines={lines} onChange={(next) => (setLines(next), setDirty(true))} taxRates={activeRates} />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Valid until" hint="Defaults to your quotation validity setting when sent.">
          {(p) => <Input {...p} type="date" value={validUntil} onChange={(e) => (setValidUntil(e.target.value), setDirty(true))} />}
        </Field>
      </div>
      <Field label="Notes for the customer">
        {(p) => <Textarea {...p} rows={2} value={notes} onChange={(e) => (setNotes(e.target.value), setDirty(true))} />}
      </Field>
      <Field label="Terms">
        {(p) => <Textarea {...p} rows={3} value={terms} onChange={(e) => (setTerms(e.target.value), setDirty(true))} />}
      </Field>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={busy} disabled={invalid || !dirty} onClick={() => void save()}>
          Save draft
        </Button>
        {dirty ? <span className="text-sm text-muted">Unsaved changes. Totals update when you save.</span> : null}
        {invalid ? <span className="text-sm text-status-danger">Every line needs a description, quantity above 0 and a price (up to 2 decimals).</span> : null}
      </div>
      {!dirty && v.items.length > 0 && quote.capabilities.send ? <SendButton quote={quote} /> : null}
    </div>
  );
}

function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input readOnly value={url} aria-label="Customer link" className="font-mono text-xs" onFocus={(e) => e.target.select()} />
        <Button
          onClick={async () => {
            await navigator.clipboard.writeText(url);
            setCopied(true);
          }}
        >
          <Copy className="size-4" aria-hidden /> {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs text-muted">Share it with the customer, for example by WhatsApp. It works once and expires with the quotation. This is the only time it is shown.</p>
    </div>
  );
}

function SendButton({ quote }: { quote: Quotation }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState(true);
  const [result, setResult] = useState<{ url: string; sentTo: string | null; channel: string | null; skipped: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Send to customer
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o && result) router.refresh();
        }}
        title={result ? "Quotation sent" : `Send ${quote.quote_number}`}
        description={result ? undefined : `Total ${formatMoney(quote.current.total, quote.current.currency_code)}. The quotation is locked once sent; changes need a revision.`}
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          {result ? (
            <>
              {result.sentTo ? (
                <Alert tone="success">
                  Sending by {result.channel === "whatsapp" ? "WhatsApp" : "email"} to {result.sentTo}. Delivery is tracked under Notifications.
                </Alert>
              ) : null}
              {result.skipped ? <Alert tone="info">Not sent automatically: {result.skipped} Share the link yourself.</Alert> : null}
              <CopyLink url={result.url} />
              <div className="flex justify-end">
                <Button onClick={() => (setOpen(false), router.refresh())}>Done</Button>
              </div>
            </>
          ) : (
            <>
              <Checkbox
                label="Send the link to the customer"
                description="By WhatsApp or email, following the customer's consent and preferred contact method."
                checked={email}
                onChange={(e) => setEmail(e.target.checked)}
              />
              <div className="flex justify-end gap-2">
                <Button onClick={() => setOpen(false)}>Cancel</Button>
                <Button
                  variant="primary"
                  loading={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      const r = await api<{ approval_url: string; emailed_to: string | null; notification_channel: string | null; notification_skipped: string | null }>(
                        "POST",
                        `/quotations/${quote.id}/send`,
                        { email_customer: email },
                      );
                      setResult({ url: r.approval_url, sentTo: r.emailed_to, channel: r.notification_channel, skipped: r.notification_skipped });
                    } catch (e) {
                      setError(errorMessage(e));
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Send
                </Button>
              </div>
            </>
          )}
        </div>
      </Dialog>
    </>
  );
}

export function SentActions({ quote }: { quote: Quotation }) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"decision" | "link" | "revise" | null>(null);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [method, setMethod] = useState("in_person");
  const [name, setName] = useState(quote.customer.name);
  const [evidence, setEvidence] = useState("");
  const [comments, setComments] = useState("");
  const [reason, setReason] = useState("");
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const close = () => {
    setDialog(null);
    setError(null);
    setUrl(null);
  };
  const status = quote.current.status;

  return (
    <div className="flex flex-wrap gap-2">
      {quote.capabilities.record_decision ? (
        <Button variant="primary" onClick={() => setDialog("decision")}>
          Record customer decision
        </Button>
      ) : null}
      {status === "sent" && quote.capabilities.revise ? <Button onClick={() => setDialog("link")}>New customer link</Button> : null}
      {quote.capabilities.revise ? <Button onClick={() => setDialog("revise")}>Revise quotation</Button> : null}

      <Dialog
        open={dialog === "decision"}
        onOpenChange={(o) => !o && close()}
        title="Record customer decision"
        description={`For version ${quote.current.version_number}, total ${formatMoney(quote.current.total, quote.current.currency_code)}.`}
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Decision">
              {(p) => (
                <Select {...p} value={decision} onChange={(e) => setDecision(e.target.value as "approved" | "rejected")}>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </Select>
              )}
            </Field>
            <Field label="How">
              {(p) => (
                <Select {...p} value={method} onChange={(e) => setMethod(e.target.value)}>
                  {Object.entries(DECISION_METHOD)
                    .filter(([k]) => k !== "customer_link")
                    .map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label="Customer name" required>
            {(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Evidence" required hint="e.g. Signed printed quotation; phoned 081 234 5678 at 10:42.">
            {(p) => <Input {...p} value={evidence} onChange={(e) => setEvidence(e.target.value)} />}
          </Field>
          <Field label="Customer comments">
            {(p) => <Textarea {...p} rows={2} value={comments} onChange={(e) => setComments(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={close}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={name.trim().length < 2 || evidence.trim().length < 3}
              onClick={() =>
                void run(async () => {
                  await api("POST", `/quotations/${quote.id}/decisions`, {
                    decision,
                    method,
                    customer_name: name.trim(),
                    evidence: evidence.trim(),
                    comments: comments.trim() || null,
                  });
                  close();
                  router.refresh();
                })
              }
            >
              Record {decision === "approved" ? "approval" : "rejection"}
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog open={dialog === "link"} onOpenChange={(o) => !o && close()} title="New customer link" description="Earlier links for this quotation stop working.">
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          {url ? (
            <CopyLink url={url} />
          ) : (
            <div className="flex justify-end gap-2">
              <Button onClick={close}>Cancel</Button>
              <Button
                variant="primary"
                loading={busy}
                onClick={() =>
                  void run(async () => {
                    setUrl((await api<{ approval_url: string }>("POST", `/quotations/${quote.id}/links`)).approval_url);
                  })
                }
              >
                Create link
              </Button>
            </div>
          )}
        </div>
      </Dialog>

      <Dialog
        open={dialog === "revise"}
        onOpenChange={(o) => !o && close()}
        title="Revise quotation"
        description={
          status === "approved"
            ? "The current approval will no longer apply. The customer must approve the new version before more chargeable work starts."
            : "A new draft version is created from this one."
        }
      >
        <div className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Reason" required hint="e.g. Discs also need replacing.">
            {(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <div className="flex justify-end gap-2">
            <Button onClick={close}>Cancel</Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={reason.trim().length < 3}
              onClick={() =>
                void run(async () => {
                  await api("POST", `/quotations/${quote.id}/revisions`, { reason: reason.trim() });
                  close();
                  router.refresh();
                })
              }
            >
              Create revision
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
