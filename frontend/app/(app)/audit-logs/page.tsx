import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { AuditLogEntry, Me, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { P, can } from "@/lib/permissions";

export const metadata: Metadata = { title: "Audit log" };

const AREAS: { value: string; label: string }[] = [
  { value: "auth.", label: "Sign-in and passwords" },
  { value: "user.", label: "Users" },
  { value: "role.", label: "Roles" },
  { value: "branch.", label: "Branches" },
  { value: "service_bay.", label: "Service bays" },
  { value: "organisation.", label: "Organisation" },
  { value: "tax_rate.", label: "Tax rates" },
  { value: "document_sequence.", label: "Numbering" },
];

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export default function AuditLogPage({ searchParams }: PageProps<"/audit-logs">) {
  return (
    <>
      <PageHeader title="Audit log" description="Security and business events, newest first. Entries cannot be edited or deleted." />
      <Suspense fallback={<PanelSkeleton rows={8} />}>
        <Content searchParams={searchParams} />
      </Suspense>
    </>
  );
}

function ChangesDetail({ changes }: { changes: AuditLogEntry["changes"] }) {
  if (!changes || Object.keys(changes).length === 0) return null;
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-steel">Details</summary>
      <pre className="mt-1 max-w-full overflow-x-auto rounded-control bg-mist p-2 font-mono whitespace-pre-wrap">
        {JSON.stringify(changes, null, 2)}
      </pre>
    </details>
  );
}

function Actor({ entry }: { entry: AuditLogEntry }) {
  return <>{entry.actor_name ?? (entry.actor_type === "cli" ? "Installer (command line)" : "System")}</>;
}

async function Content({ searchParams }: { searchParams: PageProps<"/audit-logs">["searchParams"] }) {
  const me: Me = await requireMe();
  if (!can(me, P.AUDIT_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const area = AREAS.find((a) => a.value === params.area)?.value;
  const from = typeof params.from === "string" && DATE_RE.test(params.from) ? params.from : undefined;
  const to = typeof params.to === "string" && DATE_RE.test(params.to) ? params.to : undefined;
  const page = Math.max(1, Number(params.page) || 1);

  // Date inputs are whole days; the range end is exclusive, so add one day to "to".
  const toExclusive = to ? new Date(Date.parse(`${to}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10) : undefined;
  const data = await apiGet<Page<AuditLogEntry>>(
    `/audit-logs${query({ action: area, created_from: from, created_to: toExclusive, page, page_size: 50 })}`,
  );

  return (
    <>
      <form method="get" className="mb-4 grid gap-2 sm:grid-cols-[14rem_10rem_10rem_auto] sm:items-end">
        <label className="text-sm">
          <span className="mb-1 block font-medium">Area</span>
          <Select name="area" defaultValue={area ?? ""}>
            <option value="">All areas</option>
            {AREAS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block font-medium">From</span>
          <Input type="date" name="from" defaultValue={from} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block font-medium">To</span>
          <Input type="date" name="to" defaultValue={to} />
        </label>
        <div className="flex gap-2">
          <Button type="submit">Filter</Button>
          {area || from || to ? (
            <Button asChild variant="ghost">
              <Link href="/audit-logs">Clear</Link>
            </Button>
          ) : null}
        </div>
      </form>
      <p className="mb-2 text-xs text-muted">Dates are in UTC. Times below are shown in {me.organisation.timezone}.</p>

      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title="No events match these filters" />
        ) : (
          <>
            <table className="hidden w-full text-left md:table">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium whitespace-nowrap">Time</th>
                  <th className="px-4 py-2.5 font-medium">Who</th>
                  <th className="px-4 py-2.5 font-medium">What happened</th>
                  <th className="px-4 py-2.5 font-medium">IP address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border align-top">
                {data.items.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-2.5 text-sm whitespace-nowrap tabular-nums">{formatDateTime(e.created_at, me.organisation)}</td>
                    <td className="px-4 py-2.5 text-sm">
                      <Actor entry={e} />
                    </td>
                    <td className="px-4 py-2.5 text-sm">
                      {e.summary}
                      <span className="ml-2 font-mono text-xs text-muted">{e.action}</span>
                      <ChangesDetail changes={e.changes} />
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted">{e.ip_address ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-border md:hidden">
              {data.items.map((e) => (
                <li key={e.id} className="px-4 py-3 text-sm">
                  <p>{e.summary}</p>
                  <p className="mt-0.5 text-xs text-muted tabular-nums">
                    {formatDateTime(e.created_at, me.organisation)} · <Actor entry={e} />
                  </p>
                  <ChangesDetail changes={e.changes} />
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="border-t border-border">
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            hrefFor={(p) => `/audit-logs${query({ area, from, to, page: p })}`}
          />
        </div>
      </Panel>
    </>
  );
}
