import { StatusBadge, type StatusTone } from "@/components/status-badge";
import type { RoleAssignment, UserStatus } from "@/lib/api/types";

const STATUS: Record<UserStatus, { tone: StatusTone; label: string }> = {
  active: { tone: "success", label: "Active" },
  invited: { tone: "waiting", label: "Invited" },
  deactivated: { tone: "neutral", label: "Deactivated" },
};

export function UserStatusBadge({ status }: { status: UserStatus }) {
  const s = STATUS[status];
  return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>;
}

export function describeAssignment(a: RoleAssignment): string {
  return a.branch_name ? `${a.role_name} · ${a.branch_name}` : `${a.role_name} · All branches`;
}
