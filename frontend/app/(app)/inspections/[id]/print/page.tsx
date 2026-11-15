import type { Metadata } from "next";
import { Fragment, Suspense } from "react";

import { PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { InspectionDetail } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { KIND_LABEL, RESULT_LABEL } from "@/lib/inspection";
import { formatKm, vehicleTitle } from "@/lib/labels";

import { PrintButton } from "./print-button";

export const metadata: Metadata = { title: "Inspection report" };

export default function InspectionReportPage({ params }: PageProps<"/inspections/[id]/print">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Report params={params} />
    </Suspense>
  );
}

/** Customer-readable report. Print or "Save as PDF" from the browser. */
async function Report({ params }: { params: PageProps<"/inspections/[id]/print">["params"] }) {
  const me = await requireMe();
  const { id } = await params;
  const i = await apiGet<InspectionDetail>(`/inspections/${id}`);
  const prefs = me.organisation;
  const flagged = i.items.filter((x) => x.result === "fail" || x.result === "attention");
  const sections = [...new Set(i.items.map((x) => x.section))];
  const mark: Record<string, string> = { pass: "Pass", attention: "Attention", fail: "Failed", not_inspected: "—" };

  return (
    <article className="mx-auto max-w-3xl bg-surface p-6 text-[13px] print:max-w-none print:p-0">
      <div className="mb-4 flex items-start justify-between gap-4 print:hidden">
        <p className="text-sm text-muted">Use your browser&apos;s print dialog to print or save as PDF.</p>
        <PrintButton />
      </div>
      <header className="border-b-2 border-slate-deep pb-3">
        <p className="text-lg font-semibold">{i.organisation_name}</p>
        <p className="text-muted">{i.branch_name}</p>
        <h1 className="mt-3 text-xl font-semibold">{KIND_LABEL[i.kind]} report</h1>
      </header>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
        <div><dt className="text-muted">Customer</dt><dd>{i.customer_name}</dd></div>
        <div><dt className="text-muted">Vehicle</dt><dd><span className="font-mono">{vehicleTitle(i.vehicle)}</span> {i.vehicle.make} {i.vehicle.model}</dd></div>
        <div><dt className="text-muted">Job number</dt><dd className="font-mono">{i.job_card.job_number}</dd></div>
        <div><dt className="text-muted">Odometer</dt><dd className="font-mono">{formatKm(i.odometer_km)}</dd></div>
        <div><dt className="text-muted">Inspected</dt><dd>{formatDateTime(i.submitted_at ?? i.created_at, prefs)}</dd></div>
        <div><dt className="text-muted">Inspector</dt><dd>{i.submitted_by ?? i.started_by}</dd></div>
      </dl>
      {i.status !== "submitted" ? <p className="mt-3 font-semibold">Draft – not yet submitted.</p> : null}

      <section className="mt-5">
        <h2 className="font-semibold">Summary</h2>
        <p className="mt-1">
          {i.counts.fail} failed · {i.counts.attention} need attention · {i.counts.pass} passed · {i.counts.not_inspected} not inspected
        </p>
        {i.summary ? <p className="mt-2 whitespace-pre-line">{i.summary}</p> : null}
      </section>

      {flagged.length ? (
        <section className="mt-5">
          <h2 className="font-semibold">Items needing attention</h2>
          <ul className="mt-1 space-y-2">
            {flagged.map((x) => (
              <li key={x.id} className="break-inside-avoid border-l-4 pl-3" style={{ borderColor: x.result === "fail" ? "#DC2626" : "#EAB308" }}>
                <p className="font-medium">
                  {RESULT_LABEL[x.result]}: {x.label} <span className="text-muted">({x.section})</span>
                </p>
                {x.notes ? <p className="whitespace-pre-line">{x.notes}</p> : null}
                {x.photos.length ? (
                  <div className="mt-1 flex flex-wrap gap-2">
                    {x.photos.map((p) => (
                      // eslint-disable-next-line @next/next/no-img-element -- authenticated API image
                      <img key={p.id} src={`/api/v1/files/${p.file_id}?variant=thumb`} alt={x.label} className="h-28 rounded border border-border" />
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="mt-5">
        <h2 className="font-semibold">Full checklist</h2>
        <table className="mt-1 w-full border-collapse">
          <tbody>
            {sections.map((s) => (
              <Fragment key={s}>
                <tr>
                  <th colSpan={2} className="border-b border-border pt-3 pb-1 text-left font-semibold">
                    {s}
                  </th>
                </tr>
                {i.items
                  .filter((x) => x.section === s)
                  .map((x) => (
                    <tr key={x.id} className="break-inside-avoid border-b border-border/60">
                      <td className="py-1 pr-3">{x.label}</td>
                      <td className="w-24 py-1 text-right font-medium">{mark[x.result]}</td>
                    </tr>
                  ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
      <footer className="mt-6 border-t border-border pt-2 text-xs text-muted">
        This report describes the vehicle&apos;s condition at the time of inspection.
      </footer>
    </article>
  );
}
