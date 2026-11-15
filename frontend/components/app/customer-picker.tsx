"use client";

import { useEffect, useId, useState } from "react";

import { Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { CustomerSummary, Page } from "@/lib/api/types";
import { formatPhone } from "@/lib/labels";

export interface PickedCustomer {
  id: string;
  display_name: string;
}

/**
 * Search-as-you-type customer selector (name, phone, email or registration).
 * Keyboard: type, then Tab/arrow into the result buttons and press Enter.
 */
export function CustomerPicker({
  value,
  onChange,
  excludeId,
  invalid,
  inputId,
}: {
  value: PickedCustomer | null;
  onChange: (customer: PickedCustomer | null) => void;
  excludeId?: string;
  invalid?: boolean;
  inputId?: string;
}) {
  const generatedId = useId();
  const id = inputId ?? generatedId;
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<CustomerSummary[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    if (term.trim().length < 2) return;
    const handle = setTimeout(() => {
      setStatus("loading");
      api<Page<CustomerSummary>>("GET", `/customers?search=${encodeURIComponent(term.trim())}&page_size=8`)
        .then((page) => {
          setResults(page.items.filter((c) => c.id !== excludeId));
          setStatus("idle");
        })
        .catch(() => setStatus("error"));
    }, 250);
    return () => clearTimeout(handle);
  }, [term, excludeId]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-control border border-border bg-mist px-3 py-2">
        <span className="font-medium">{value.display_name}</span>
        <button type="button" className="text-sm text-steel hover:underline" onClick={() => onChange(null)}>
          Change
        </button>
      </div>
    );
  }

  const showResults = term.trim().length >= 2;
  return (
    <div>
      <Input
        id={id}
        type="search"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Search by name, phone or registration"
        aria-invalid={invalid || undefined}
        aria-controls={`${id}-results`}
        autoComplete="off"
      />
      {showResults ? (
        <div id={`${id}-results`} aria-live="polite" className="mt-1 rounded-control border border-border bg-surface">
          {status === "loading" ? <p className="px-3 py-2 text-sm text-muted">Searching…</p> : null}
          {status === "error" ? <p className="px-3 py-2 text-sm text-status-danger">Search failed. Try again.</p> : null}
          {status === "idle" && results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted">No matching customers.</p>
          ) : null}
          <ul className="divide-y divide-border">
            {results.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-mist focus:bg-mist"
                  onClick={() => onChange({ id: c.id, display_name: c.display_name })}
                >
                  <span className="font-medium">{c.display_name}</span>
                  <span className="font-mono text-xs text-muted">{c.primary_phone ? formatPhone(c.primary_phone) : ""}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
