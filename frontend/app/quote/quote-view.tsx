"use client";

import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/page";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { PublicQuotation } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { LINE_KIND, QUOTE_STATUS } from "@/lib/quotation";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; token: string; quote: PublicQuotation };

function tokenFromHash(): string | null {
  return new URLSearchParams(window.location.hash.slice(1)).get("token");
}

function date(value: string): string {
  const [y, m, d] = value.split("-");
  return `${d}/${m}/${y}`;
}

export function QuoteView() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [name, setName] = useState("");
  const [comments, setComments] = useState("");
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = tokenFromHash();
    const load: Promise<State> = token
      ? api<PublicQuotation>("POST", "/public/quotations/view", { token }).then(
          (quote): State => ({ kind: "ready", token, quote }),
          (e: unknown): State => ({ kind: "error", message: errorMessage(e) }),
        )
      : Promise.resolve({ kind: "error", message: "This link is incomplete. Open it again from your message." });
    void load.then(setState);
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (state.kind === "error") return <Alert tone="error" title="This quotation link cannot be used">{state.message}</Alert>;

  const { quote: q, token } = state;
  const c = q.currency_code;
  const st = QUOTE_STATUS[q.status];

  async function decide(decision: "approved" | "rejected") {
    setBusy(decision);
    setError(null);
    try {
      const quote = await api<PublicQuotation>("POST", "/public/quotations/decision", {
        token,
        decision,
        customer_name: name.trim(),
        comments: comments.trim() || null,
        accept_terms: accept,
      });
      setState({ kind: "ready", token, quote });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="space-y-5">
      <header>
        <p className="font-semibold">{q.organisation_name}</p>
        <p className="text-sm text-muted">
          {q.branch_name}
          {q.organisation_phone ? ` · ${q.organisation_phone}` : ""}
          {q.organisation_email ? ` · ${q.organisation_email}` : ""}
        </p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">
            Quotation <span className="font-mono">{q.quote_number}</span>
            {q.version_number > 1 ? <span className="text-sm font-normal text-muted"> (version {q.version_number})</span> : null}
          </h1>
          <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
        </div>
        <p className="text-sm">
          For {q.customer_name} · {q.vehicle}
        </p>
        {q.valid_until ? <p className="text-sm text-muted">Valid until {date(q.valid_until)}</p> : null}
      </header>

      <section className="rounded-panel border border-border bg-surface p-4">
        <ul className="divide-y divide-border">
          {q.items.map((i, idx) => (
            <li key={idx} className="flex justify-between gap-3 py-2 text-sm">
              <div>
                <p>{i.description}</p>
                <p className="text-xs text-muted">
                  {LINE_KIND[i.kind]} · {i.quantity} × {formatMoney(i.unit_price, c)}
                </p>
              </div>
              <span className="font-mono tabular-nums">{formatMoney(i.line_total, c)}</span>
            </li>
          ))}
        </ul>
        <dl className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted">Subtotal (excl. tax)</dt>
            <dd className="font-mono tabular-nums">{formatMoney(q.subtotal, c)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted">Tax</dt>
            <dd className="font-mono tabular-nums">{formatMoney(q.tax_total, c)}</dd>
          </div>
          <div className="flex justify-between text-lg font-semibold">
            <dt>Total</dt>
            <dd className="font-mono tabular-nums">{formatMoney(q.total, c)}</dd>
          </div>
        </dl>
        {q.notes ? <p className="mt-3 text-sm whitespace-pre-line">{q.notes}</p> : null}
        {q.terms ? <p className="mt-3 border-t border-border pt-3 text-xs whitespace-pre-line text-muted">{q.terms}</p> : null}
      </section>

      {q.decision ? (
        <Alert tone={q.decision === "approved" ? "success" : "info"} title={q.decision === "approved" ? "You approved this quotation" : "You declined this quotation"}>
          The workshop has been notified. Contact them if anything changes.
        </Alert>
      ) : q.can_decide ? (
        <section className="space-y-4 rounded-panel border border-border bg-surface p-4">
          <h2 className="font-semibold">Your decision</h2>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Field label="Your full name" required>
            {(p) => <Input {...p} value={name} autoComplete="name" onChange={(e) => setName(e.target.value)} />}
          </Field>
          <Field label="Comments for the workshop">
            {(p) => <Textarea {...p} rows={2} value={comments} onChange={(e) => setComments(e.target.value)} />}
          </Field>
          <Checkbox
            label={`I approve the work in this quotation for ${formatMoney(q.total, c)} and accept its terms.`}
            checked={accept}
            onChange={(e) => setAccept(e.target.checked)}
          />
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="primary" loading={busy === "approved"} disabled={!accept || name.trim().length < 2 || busy !== null} onClick={() => void decide("approved")}>
              Approve quotation
            </Button>
            <Button variant="danger" loading={busy === "rejected"} disabled={name.trim().length < 2 || busy !== null} onClick={() => void decide("rejected")}>
              Decline
            </Button>
          </div>
          <p className="text-xs text-muted">Your name, the time and your device details are recorded with your decision.</p>
        </section>
      ) : (
        <Alert tone="info" title="This quotation can no longer be approved online">
          Please contact the workshop.
        </Alert>
      )}
    </article>
  );
}
