import { StatusBadge } from "@/components/status-badge";
import type { JobStatus } from "@/lib/api/types";
import { JOB_STATUS_LABEL, JOB_STATUS_TONE } from "@/lib/job-status";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <StatusBadge tone={JOB_STATUS_TONE[status]}>{JOB_STATUS_LABEL[status]}</StatusBadge>;
}

export function OverdueBadge() {
  return <StatusBadge tone="danger">Overdue</StatusBadge>;
}
