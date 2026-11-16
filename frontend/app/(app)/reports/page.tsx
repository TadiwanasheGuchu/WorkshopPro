import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { NoAccess, PageHeader, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { FinancialReport, InventoryReport, JobStatus, Me, OperationsReport } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { PAYMENT_METHOD } from "@/lib/invoice";
import { MOVEMENT_LABEL, qty, signedQty } from "@/lib/inventory";
import { JOB_STATUS_LABEL } from "@/lib/job-status";
import { isDate, localToday, presets } from "@/lib/period";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Reports" };

type View = "financial" | "operations" | "inventory";
const VIEW_LABEL: Record<View, string> = { financial: "Financial", operations: "Operations", inventory: "Inventory" };

export default function ReportsPage({ searchParams }: PageProps<"/reports">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/reports">["searchParams"] }) {
  const me = await requireMe();
  const views: View[] = [];
  if (canInAnyBranch(me, P.REPORTS_FINANCIAL)) views.push("financial");
  if (canInAnyBranch(me, P.REPORTS_OPERATIONAL)) views.push("operations");
  if (canInAnyBranch(me, P.REPORTS_INVENTORY)) views.push("inventory");
  if (!views.length) return <NoAccess />;

  const params = await searchParams;
  const view: View = views.includes(params.view as View) ? (params.view as View) : views[0];
  const today = localToday(me.organisation.timezone);
  const all = presets(today);
  const thisMonth = all[1];
  const from = isDate(params.from) ? params.from : thisMonth.from;
  const to = isDate(params.to) ? params.to : thisMonth.to;
  const branch = typeof params.branch === "string" && me.branches.some((b) => b.id === params.branch) ? params.branch : undefined;
  const href = (over: Record<string, string | undefined>) => `/reports${query({ view, from, to, branch, ...over })}`;

  return (
    <>
      <PageHeader title="Reports" description={`Dates are inclusive, in ${me.organisation.timezone} time.`} />
      {views.length > 1 ? (
        <TabNav
          tabs={views.map((v) => ({ href: href({ view: v }), label: VIEW_LABEL[v] }))}
          active={href({ view })}
        />
      ) : null}

      <form method="get" className="mb-3 flex flex-wrap items-end gap-2">
        <input type="hidden" name="view" value={view} />
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">From</span>
          <Input type="date" name="from" defaultValue={from} max={today} required />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">To</span>
          <Input type="date" name="to" defaultValue={to} required />
        </label>
        {me.branches.length > 1 ? (
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Branch</span>
            <Select name="branch" defaultValue={branch ?? ""}>
              <option value="">All my branches</option>
              {me.branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </label>
        ) : null}
        <Button type="submit">Show</Button>
      </form>
      <nav aria-label="Period presets" className="mb-5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {all.map((p) => (
          <Link key={p.key} href={href({ from: p.from, to: p.to })} className={p.from === from && p.to === to ? "font-semibold text-slate-deep" : "text-steel hover:underline"} aria-current={p.from === from && p.to === to ? "true" : undefined}>
            {p.label}
          </Link>
        ))}
      </nav>

      {view === "financial" ? (
        <Financial me={me} params={{ date_from: from, date_to: to, branch_id: branch }} />
      ) : view === "operations" ? (
        <Operations me={me} params={{ date_from: from, date_to: to, branch_id: branch }} />
      ) : (
        <Inventory me={me} params={{ date_from: from, date_to: to, branch_id: branch }} />
      )}
    </>
  );
}

type Params = { date_from: string; date_to: string; branch_id?: string };

function Figures({ rows }: { rows: { label: string; value: ReactNode; strong?: boolean; href?: string }[] }) {
  return (
    <dl className="divide-y divide-border text-sm">
      {rows.map((r) => (
        <div key={r.label} className={`flex justify-between gap-4 px-4 py-2 ${r.strong ? "font-semibold" : ""}`}>
          <dt className={r.strong ? "" : "text-muted"}>
            {r.href ? (
              <Link href={r.href} className="text-steel hover:underline">
                {r.label}
              </Link>
            ) : (
              r.label
            )}
          </dt>
          <dd className="font-mono tabular-nums">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Definitions({ items }: { items: { term: string; definition: string }[] }) {
  return (
    <details className="mt-5 text-sm">
      <summary className="cursor-pointer text-steel">How these figures are calculated</summary>
      <dl className="mt-2 space-y-2">
        {items.map((d) => (
          <div key={d.term}>
            <dt className="font-medium">{d.term}</dt>
            <dd className="text-muted">{d.definition}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

async function Financial({ me, params }: { me: Me; params: Params }) {
  const r = await apiGet<FinancialReport>(`/reports/financial${query(params)}`);
  const c = r.currency_code;
  const m = (v: string) => formatMoney(v, c);
  // Deductions: shown negative, but never as "-N$ 0.00".
  const less = (v: string) => formatMoney(Number(v) ? `-${v}` : v, c);
  const prefs = me.organisation;
  const period = `${formatDate(r.period.date_from, prefs)} to ${formatDate(r.period.date_to, prefs)}`;

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title={`Invoiced · ${period}`} flush>
          <Figures
            rows={[
              { label: `Invoices issued (${r.invoiced.count})`, value: m(r.invoiced.total) },
              { label: "of which tax", value: m(r.invoiced.tax_total) },
              { label: `Credit notes (${r.credited.count})`, value: less(r.credited.total) },
              { label: "Net invoiced", value: m(r.net_invoiced), strong: true },
            ]}
          />
        </Panel>
        <Panel title={`Cash · ${period}`} flush>
          <Figures
            rows={[
              { label: `Payments received (${r.received.count})`, value: m(r.received.total) },
              { label: `Refunds (${r.refunded.count})`, value: less(r.refunded.total) },
              { label: `Reversed in error (${r.reversed.count})`, value: less(r.reversed.total) },
              { label: "Net received", value: m(r.net_received), strong: true },
            ]}
          />
        </Panel>
        <Panel title={`Receivables as at ${formatDate(r.receivables.as_at, prefs)}`} flush>
          <Figures
            rows={[
              { label: `Outstanding (${r.receivables.open_invoices} invoices)`, value: m(r.receivables.outstanding), strong: true, href: "/invoices?status=outstanding" },
              { label: "Overdue", value: m(r.receivables.overdue), href: "/invoices?status=overdue" },
              ...r.receivables.ageing.map((a) => ({ label: `${a.bucket} (${a.count})`, value: m(a.amount) })),
              { label: "Unapplied customer credit", value: m(r.receivables.unapplied_credit) },
            ]}
          />
        </Panel>
        <Panel title="By payment method" flush>
          {r.by_method.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No payments in this period.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Method</th>
                  <th className="px-4 py-2 text-right font-medium">Received</th>
                  <th className="px-4 py-2 text-right font-medium">Paid out</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {r.by_method.map((row) => (
                  <tr key={row.method}>
                    <td className="px-4 py-2">{PAYMENT_METHOD[row.method]}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{m(row.received)}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{m(row.paid_out)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Panel title="By day" flush className="mt-5">
        {r.daily.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">No invoices or payments in this period.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border text-xs text-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Date</th>
                <th className="px-4 py-2 text-right font-medium">Invoiced</th>
                <th className="px-4 py-2 text-right font-medium">Received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {r.daily.map((d) => (
                <tr key={d.date}>
                  <td className="px-4 py-2">{formatDate(d.date, prefs)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{m(d.invoiced)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{m(d.received)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <Definitions items={r.definitions} />
    </>
  );
}

function hours(h: number | null): string {
  if (h === null) return "—";
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} days`;
}

async function Operations({ me, params }: { me: Me; params: Params }) {
  const r = await apiGet<OperationsReport>(`/reports/operations${query(params)}`);
  const prefs = me.organisation;
  const period = `${formatDate(r.period.date_from, prefs)} to ${formatDate(r.period.date_to, prefs)}`;
  const open = Object.entries(r.open_by_status) as [JobStatus, number][];
  const decided = r.quotations.approved + r.quotations.rejected;

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title={`Jobs · ${period}`} flush>
          <Figures
            rows={[
              { label: "Received", value: r.received },
              { label: "Completed (collected)", value: r.completed },
              { label: "Cancelled", value: r.cancelled },
              { label: "Turnaround, average", value: hours(r.turnaround_hours_avg) },
              { label: "Turnaround, median", value: hours(r.turnaround_hours_median) },
            ]}
          />
        </Panel>
        <Panel title={`Quotations · ${period}`} flush>
          <Figures
            rows={[
              { label: "Sent", value: r.quotations.sent },
              { label: "Approved", value: r.quotations.approved },
              { label: "Rejected", value: r.quotations.rejected },
              { label: "Approval rate", value: decided ? `${Math.round((r.quotations.approved / decided) * 100)}%` : "—" },
              { label: "Approved value", value: formatMoney(r.quotations.approved_value, r.currency_code) },
            ]}
          />
        </Panel>
        <Panel title="Open jobs now" flush>
          <Figures
            rows={[
              ...open.map(([s, n]) => ({ label: JOB_STATUS_LABEL[s], value: n, href: `/job-cards?status=${s}` })),
              { label: "Overdue (past promised time)", value: r.overdue_now },
              { label: "Total open", value: r.open_total, strong: true },
            ]}
          />
        </Panel>
        <Panel title="Mechanic workload" flush>
          {r.mechanics.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No assigned jobs.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Mechanic</th>
                  <th className="px-4 py-2 text-right font-medium">Open now</th>
                  <th className="px-4 py-2 text-right font-medium">Completed in period</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {r.mechanics.map((row) => (
                  <tr key={row.user_id}>
                    <td className="px-4 py-2">{row.name}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{row.open_jobs}</td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{row.completed_in_period}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
      <Definitions items={r.definitions} />
    </>
  );
}

async function Inventory({ me, params }: { me: Me; params: Params }) {
  const r = await apiGet<InventoryReport>(`/reports/inventory${query(params)}`);
  const c = r.currency_code;
  const m = (v: string) => formatMoney(v, c);
  const prefs = me.organisation;
  const period = `${formatDate(r.period.date_from, prefs)} to ${formatDate(r.period.date_to, prefs)}`;
  const v = r.valuation;
  const rec = r.reconciliation;
  const reconciled = rec.on_hand_mismatches === 0 && rec.reserved_mismatches === 0;
  const p = r.purchasing;

  return (
    <>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title={`Stock value as at ${formatDate(v.as_at, prefs)}`} flush>
          <Figures
            rows={[
              ...v.by_location.map((l) => ({ label: `${l.location.name} · ${l.branch.name} (${qty(l.units)} units)`, value: m(l.value) })),
              { label: `Parts in stock (${v.parts_in_stock})`, value: m(v.total_value), strong: true },
              { label: "Parts at or below minimum", value: r.low_stock_parts, href: "/inventory/parts?low=1" },
            ]}
          />
        </Panel>
        <Panel title="Value by category" flush>
          {v.by_category.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No stock on hand.</p>
          ) : (
            <Figures rows={v.by_category.map((x) => ({ label: `${x.category} (${x.parts} ${x.parts === 1 ? "part" : "parts"})`, value: m(x.value) }))} />
          )}
        </Panel>
        <Panel title={`Stock movements · ${period}`} flush>
          {r.movements.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No stock movements in this period.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Type</th>
                  <th className="px-4 py-2 text-right font-medium">Quantity</th>
                  <th className="px-4 py-2 text-right font-medium">Value at cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {r.movements.map((row) => (
                  <tr key={row.kind}>
                    <td className="px-4 py-2">
                      <Link href={`/inventory/movements?kind=${row.kind}`} className="text-steel hover:underline">
                        {MOVEMENT_LABEL[row.kind]}
                      </Link>{" "}
                      <span className="text-xs text-muted">({row.count})</span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">{signedQty(row.quantity)}</td>
                    <td className="px-4 py-2 text-right font-mono whitespace-nowrap tabular-nums">{m(row.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        <Panel title={`Purchasing · ${period}`} flush>
          <Figures
            rows={[
              { label: `Orders approved (${p.orders_approved})`, value: m(p.approved_value) },
              { label: "Deliveries received", value: m(p.received_value) },
              { label: "Returned to suppliers", value: m(p.returned_value) },
              { label: `Still on order now (${p.open_orders})`, value: m(p.open_value), href: "/purchase-orders?status=open" },
              { label: "Overdue orders now", value: p.overdue_orders },
            ]}
          />
        </Panel>
        <Panel title={`Most used parts · ${period}`} flush>
          {r.usage.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No parts issued to jobs in this period.</p>
          ) : (
            <Figures rows={r.usage.map((u) => ({ label: `${u.sku} ${u.part.name} (${qty(u.quantity)})`, value: m(u.cost_value), href: `/inventory/parts/${u.part.id}` }))} />
          )}
        </Panel>
        <Panel title="Stock check" flush>
          <Figures
            rows={[
              { label: "Stock levels checked", value: rec.stock_levels_checked },
              { label: "On hand differs from ledger", value: rec.on_hand_mismatches },
              { label: "Reserved differs from open reservations", value: rec.reserved_mismatches },
              { label: reconciled ? "Stock matches the ledger" : "Differences found: contact support", value: reconciled ? "OK" : "Check", strong: true },
            ]}
          />
        </Panel>
      </div>
      <Definitions items={r.definitions} />
    </>
  );
}
