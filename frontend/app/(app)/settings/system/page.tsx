import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { NoAccess, Panel, PanelSkeleton } from "@/components/ui/page";
import { getReadiness } from "@/lib/api/health";
import { requireMe } from "@/lib/auth";
import { P, can } from "@/lib/permissions";

export const metadata: Metadata = { title: "System status" };

const LABELS: Record<string, string> = { database: "PostgreSQL database", redis: "Redis" };

export default function SystemStatusPage() {
  return (
    <Suspense fallback={<PanelSkeleton rows={3} />}>
      <Content />
    </Suspense>
  );
}

async function Content() {
  await connection();
  const me = await requireMe();
  if (!can(me, P.SETTINGS_VIEW)) return <NoAccess />;
  const result = await getReadiness();
  const rows: { label: string; ok: boolean; note?: string }[] = result.reachable
    ? [
        { label: "API", ok: true },
        ...Object.entries(result.readiness.checks).map(([name, c]) => ({
          label: LABELS[name] ?? name,
          ok: c.status === "ok",
          note: c.latency_ms != null ? `${c.latency_ms} ms` : undefined,
        })),
      ]
    : [{ label: "API", ok: false, note: result.reason }];

  return (
    <div className="max-w-3xl">
      <Panel title="Services" flush>
        <ul className="divide-y divide-border">
          {rows.map((r) => (
            <li key={r.label} className="flex items-center justify-between gap-4 px-4 py-2.5">
              <span>{r.label}</span>
              <span className="flex items-center gap-3">
                {r.note ? <span className="font-mono text-xs tabular-nums text-muted">{r.note}</span> : null}
                <StatusBadge tone={r.ok ? "success" : "danger"}>{r.ok ? "Connected" : "Unavailable"}</StatusBadge>
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
