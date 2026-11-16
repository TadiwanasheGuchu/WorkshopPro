"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { api } from "@/lib/api/client";
import type { Page, PartListItem } from "@/lib/api/types";
import { qty } from "@/lib/inventory";

/** Search the catalogue by SKU or name. Stock shown is across the user's branches. */
export function PartPicker({ value, onChange }: { value: PartListItem | null; onChange: (p: PartListItem | null) => void }) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PartListItem[]>([]);
  useEffect(() => {
    if (term.trim().length < 2) return;
    const t = setTimeout(() => {
      void api<Page<PartListItem>>("GET", `/inventory/parts?search=${encodeURIComponent(term.trim())}&page_size=8`)
        .then((r) => setResults(r.items))
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [term]);

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-control border border-border px-3 py-2 text-sm">
        <span>
          <span className="font-mono">{value.sku}</span> {value.name}
        </span>
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
          Change
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <Input aria-label="Search parts" placeholder="Search SKU or name" value={term} onChange={(e) => setTerm(e.target.value)} autoFocus />
      {term.trim().length >= 2 && results.length ? (
        <ul className="max-h-56 divide-y divide-border overflow-y-auto rounded-control border border-border">
          {results.map((p) => (
            <li key={p.id}>
              <button type="button" className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-mist" onClick={() => onChange(p)}>
                <span>
                  <span className="font-mono">{p.sku}</span> {p.name}
                </span>
                <span className="font-mono text-xs text-muted">{qty(p.stock.available)} avail.</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

