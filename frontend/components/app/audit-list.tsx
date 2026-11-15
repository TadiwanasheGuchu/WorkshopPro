import type { AuditLogEntry, Me } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

/** Compact audit trail for a record's detail page. */
export function AuditList({ entries, me }: { entries: AuditLogEntry[]; me: Me }) {
  if (entries.length === 0) return <p className="px-4 py-4 text-sm text-muted">No recorded activity.</p>;
  return (
    <ol className="divide-y divide-border">
      {entries.map((e) => (
        <li key={e.id} className="px-4 py-2.5 text-sm">
          <p>{e.summary}</p>
          <p className="text-xs text-muted tabular-nums">
            {formatDateTime(e.created_at, me.organisation)} · {e.actor_name ?? (e.actor_type === "cli" ? "Installer" : "System")}
          </p>
        </li>
      ))}
    </ol>
  );
}
