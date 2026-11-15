import { connection } from "next/server";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { getReadiness } from "@/lib/api/health";

/*
 * Phase 0 system status page. Replaced by the dashboard and sign-in flow in Phase 1.
 */

export default function Home() {
  return (
    <div className="min-h-full">
      <header className="bg-slate-deep text-white">
        <div className="mx-auto flex h-12 max-w-5xl items-center px-4">
          <span className="text-sm font-semibold tracking-wide">WORKSHOPPRO</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <h1 className="text-lg font-semibold">System status</h1>
        <p className="mt-1 text-muted">
          Foundation build. Sign-in, organisation setup and the workshop dashboard arrive in
          Phase 1.
        </p>

        <section
          aria-labelledby="dependencies-heading"
          className="mt-5 rounded-panel border border-border bg-surface"
        >
          <h2
            id="dependencies-heading"
            className="border-b border-border px-4 py-2.5 text-sm font-semibold"
          >
            Services
          </h2>
          <Suspense fallback={<StatusRowsSkeleton />}>
            <StatusRows />
          </Suspense>
        </section>
      </main>
    </div>
  );
}

const SERVICE_LABELS: Record<string, string> = {
  database: "PostgreSQL database",
  redis: "Redis",
};

async function StatusRows() {
  await connection();
  const result = await getReadiness();

  if (!result.reachable) {
    return (
      <ul className="divide-y divide-border">
        <StatusRow label="API" tone="danger" status="Unavailable" note={result.reason} />
      </ul>
    );
  }

  const { checks } = result.readiness;
  return (
    <ul className="divide-y divide-border">
      <StatusRow label="API" tone="success" status="Running" />
      {Object.entries(checks).map(([name, check]) => (
        <StatusRow
          key={name}
          label={SERVICE_LABELS[name] ?? name}
          tone={check.status === "ok" ? "success" : "danger"}
          status={check.status === "ok" ? "Connected" : "Unavailable"}
          note={check.latency_ms != null ? `${check.latency_ms} ms` : undefined}
        />
      ))}
    </ul>
  );
}

function StatusRow({
  label,
  tone,
  status,
  note,
}: {
  label: string;
  tone: "success" | "danger";
  status: string;
  note?: string;
}) {
  return (
    <li className="flex items-center justify-between gap-4 px-4 py-2.5">
      <span>{label}</span>
      <span className="flex items-center gap-3">
        {note ? <span className="font-mono text-xs tabular-nums text-muted">{note}</span> : null}
        <StatusBadge tone={tone}>{status}</StatusBadge>
      </span>
    </li>
  );
}

function StatusRowsSkeleton() {
  return (
    <ul className="divide-y divide-border" aria-busy="true" aria-label="Checking services">
      {["API", "PostgreSQL database", "Redis"].map((label) => (
        <li key={label} className="flex items-center justify-between px-4 py-2.5">
          <span>{label}</span>
          <StatusBadge tone="neutral">Checking</StatusBadge>
        </li>
      ))}
    </ul>
  );
}
