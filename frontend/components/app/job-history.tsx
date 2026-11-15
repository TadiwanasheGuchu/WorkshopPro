import Link from "next/link";

import { JobStatusBadge } from "@/components/app/job-status-badge";
import type { JobCardSummary, Me } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { vehicleTitle } from "@/lib/labels";

/** Job cards for a vehicle or customer, newest first. */
export function JobHistory({ jobs, me, showVehicle }: { jobs: JobCardSummary[]; me: Me; showVehicle?: boolean }) {
  if (jobs.length === 0) return <p className="px-4 py-3 text-sm text-muted">No job cards yet.</p>;
  return (
    <ul className="divide-y divide-border">
      {jobs.map((j) => (
        <li key={j.id}>
          <Link href={`/job-cards/${j.id}`} className="flex items-start justify-between gap-3 px-4 py-3 hover:bg-mist">
            <div className="min-w-0">
              <p>
                <span className="font-mono font-medium text-steel">{j.job_number}</span>
                {showVehicle ? <span className="font-mono text-muted"> · {vehicleTitle(j.vehicle)}</span> : null}
              </p>
              <p className="truncate text-sm text-muted">{j.complaint}</p>
            </div>
            <div className="shrink-0 text-right">
              <JobStatusBadge status={j.status} />
              <p className="mt-1 text-xs text-muted tabular-nums">{formatDate(j.received_at, me.organisation)}</p>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
