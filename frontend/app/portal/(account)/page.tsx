import type { Metadata } from "next";
import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { DateFormat, PortalHome, PortalJob } from "@/lib/api/types";
import { formatDate, formatMoney } from "@/lib/format";
import { JOB_STATUS_TONE } from "@/lib/job-status";

export const metadata: Metadata = { title: "Overview" };

export default async function PortalHomePage() {
  const [home, jobs] = await Promise.all([portalGet<PortalHome>("/home"), portalGet<PortalJob[]>("/jobs")]);
  const prefs = { timezone: home.me.timezone, date_format: home.me.date_format as DateFormat };
  const history = jobs.filter((j) => j.status === "completed");

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Hello {home.me.customer_name}</h1>

      {home.quotations_to_review.length ? (
        <Panel title="Quotations waiting for your decision" flush>
          <ul className="divide-y divide-border">
            {home.quotations_to_review.map((q) => (
              <li key={q.id}>
                <Link href={`/portal/quotations/${q.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
                  <span className="font-mono text-steel">{q.number}</span>
                  <span className="font-mono tabular-nums">{q.total ? formatMoney(q.total, home.currency_code) : ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <p className="text-sm">
        <Link href="/portal/bookings" className="text-steel hover:underline">
          Book a service
        </Link>
      </p>

      <Panel title="Your vehicles at the workshop" flush>
        {home.open_jobs.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">None of your vehicles are in the workshop right now.</p>
        ) : (
          <JobList jobs={home.open_jobs} prefs={prefs} />
        )}
      </Panel>

      {Number(home.outstanding) > 0 ? (
        <Panel title="Amount owed">
          <p className="font-mono text-lg tabular-nums">{formatMoney(home.outstanding, home.currency_code)}</p>
          <Link href="/portal/invoices" className="text-sm text-steel hover:underline">
            See invoices
          </Link>
        </Panel>
      ) : null}

      <Panel title="Your vehicles" flush>
        {home.vehicles.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">No vehicles registered.</p>
        ) : (
          <ul className="divide-y divide-border">
            {home.vehicles.map((v) => (
              <li key={v.id} className="px-4 py-3 text-sm">
                <span className="font-mono">{v.registration_number ?? v.vin}</span> {v.year ?? ""} {v.make} {v.model}
                {v.odometer_km !== null ? <span className="block text-xs text-muted">Last recorded odometer {v.odometer_km.toLocaleString("en-ZA")} km</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {history.length ? (
        <Panel title="Service history" flush>
          <JobList jobs={history} prefs={prefs} />
        </Panel>
      ) : null}

      <p className="text-sm text-muted">
        Questions? Contact {home.me.organisation_name}
        {home.me.organisation_phone ? ` on ${home.me.organisation_phone}` : ""}
        {home.me.organisation_email ? ` or ${home.me.organisation_email}` : ""}.
      </p>
    </div>
  );
}

function JobList({ jobs, prefs }: { jobs: PortalJob[]; prefs: { timezone: string; date_format: DateFormat } }) {
  return (
    <ul className="divide-y divide-border">
      {jobs.map((j) => (
        <li key={j.id}>
          <Link href={`/portal/jobs/${j.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-mist">
            <span>
              <span className="text-sm font-medium">{j.vehicle}</span>
              <span className="block text-xs text-muted">
                <span className="font-mono">{j.job_number}</span> · received {formatDate(j.received_at, prefs)}
              </span>
            </span>
            <StatusBadge tone={JOB_STATUS_TONE[j.status]}>{j.status_label}</StatusBadge>
          </Link>
        </li>
      ))}
    </ul>
  );
}
