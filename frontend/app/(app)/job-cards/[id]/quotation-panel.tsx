"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { Quotation } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { QUOTE_STATUS } from "@/lib/quotation";

export function QuotationSummary({ quote }: { quote: Quotation }) {
  const st = QUOTE_STATUS[quote.current.status];
  return (
    <Link href={`/quotations/${quote.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
      <div>
        <p className="font-mono font-medium text-steel">
          {quote.quote_number} <span className="text-xs text-muted">v{quote.current.version_number}</span>
        </p>
        <p className="text-xs text-muted">{quote.current.items.length} lines</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono tabular-nums">{formatMoney(quote.current.total, quote.current.currency_code)}</span>
        <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
      </div>
    </Link>
  );
}

export function PrepareQuotationButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-2">
      {error ? <span className="text-xs text-status-danger">{error}</span> : null}
      <Button
        size="sm"
        variant="primary"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const q = await api<Quotation>("POST", `/job-cards/${jobId}/quotation`);
            router.push(`/quotations/${q.id}`);
          } catch (e) {
            setError(errorMessage(e));
            setBusy(false);
          }
        }}
      >
        Prepare quotation
      </Button>
    </div>
  );
}
