"use client";

import { useRouter } from "next/navigation";

import type { BranchSummary } from "@/lib/api/types";
import { BRANCH_COOKIE } from "@/lib/constants";

/**
 * Selects the branch the user is working in. Stored in a cookie so server-rendered
 * lists can default to it (used by workshop screens from Phase 2). It is a view
 * filter only; the API enforces branch access independently.
 */
export function BranchSwitcher({
  branches,
  selected,
  allowAll,
}: {
  branches: BranchSummary[];
  selected: string | null;
  allowAll: boolean;
}) {
  const router = useRouter();

  if (branches.length === 0) return null;
  if (branches.length === 1 && !allowAll) {
    return <span className="text-sm text-muted">{branches[0].name}</span>;
  }

  function choose(value: string) {
    const maxAge = 60 * 60 * 24 * 365;
    document.cookie = `${BRANCH_COOKIE}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; samesite=lax`;
    router.refresh();
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only sm:not-sr-only sm:text-muted">Branch</span>
      <select
        className="h-9 rounded-control border border-border bg-surface pr-7 pl-2 text-sm"
        value={selected ?? (allowAll ? "all" : branches[0].id)}
        onChange={(e) => choose(e.target.value)}
      >
        {allowAll ? <option value="all">All branches</option> : null}
        {branches.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
    </label>
  );
}
