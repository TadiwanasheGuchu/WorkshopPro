import type { StatusTone } from "@/components/status-badge";

import type { PoStatus } from "./api/types";

export const PO_STATUS: Record<PoStatus, { tone: StatusTone; label: string }> = {
  draft: { tone: "neutral", label: "Draft" },
  approved: { tone: "active", label: "Ordered" },
  partially_received: { tone: "waiting", label: "Partly received" },
  received: { tone: "success", label: "Received" },
  closed: { tone: "neutral", label: "Closed short" },
  cancelled: { tone: "neutral", label: "Cancelled" },
};

export function poStatus(po: { status: PoStatus; is_overdue: boolean }): { tone: StatusTone; label: string } {
  return po.is_overdue ? { tone: "danger", label: "Overdue" } : PO_STATUS[po.status];
}
