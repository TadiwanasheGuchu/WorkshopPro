"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import type { BranchSummary, Role } from "@/lib/api/types";

export interface AssignmentDraft {
  role_id: string;
  branch_id: string | null;
}

/**
 * Edit a list of (role, branch) pairs. "All branches" grants the role organisation-wide.
 * The owner role can only be organisation-wide.
 */
export function RoleAssignmentsEditor({
  value,
  onChange,
  roles,
  branches,
}: {
  value: AssignmentDraft[];
  onChange: (value: AssignmentDraft[]) => void;
  roles: Role[];
  branches: BranchSummary[];
}) {
  const update = (index: number, patch: Partial<AssignmentDraft>) =>
    onChange(value.map((a, i) => (i === index ? { ...a, ...patch } : a)));

  return (
    <div className="space-y-2">
      {value.length === 0 ? <p className="text-sm text-muted">No roles assigned.</p> : null}
      {value.map((assignment, index) => {
        const role = roles.find((r) => r.id === assignment.role_id);
        return (
          <div key={index} className="flex flex-col gap-2 rounded-control border border-border p-2 sm:flex-row sm:items-center sm:border-0 sm:p-0">
            <Select
              aria-label={`Role ${index + 1}`}
              value={assignment.role_id}
              onChange={(e) => {
                const next = roles.find((r) => r.id === e.target.value);
                update(index, { role_id: e.target.value, branch_id: next?.is_owner ? null : assignment.branch_id });
              }}
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label={`Branch for role ${index + 1}`}
              value={assignment.branch_id ?? ""}
              disabled={role?.is_owner}
              onChange={(e) => update(index, { branch_id: e.target.value || null })}
            >
              <option value="">All branches</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
            <Button
              variant="ghost"
              aria-label={`Remove role ${index + 1}`}
              onClick={() => onChange(value.filter((_, i) => i !== index))}
              className="self-end sm:self-auto"
            >
              <X className="size-4" aria-hidden />
              <span className="sm:hidden">Remove</span>
            </Button>
          </div>
        );
      })}
      <Button
        size="sm"
        onClick={() => {
          const fallback = roles.find((r) => !r.is_owner) ?? roles[0];
          if (fallback) onChange([...value, { role_id: fallback.id, branch_id: branches[0]?.id ?? null }]);
        }}
      >
        <Plus className="size-4" aria-hidden /> Add role
      </Button>
    </div>
  );
}
