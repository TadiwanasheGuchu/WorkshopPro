import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PdfLink } from "@/components/app/pdf-link";
import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { PurchaseOrder } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { qty } from "@/lib/inventory";
import { P, canInAnyBranch } from "@/lib/permissions";
import { poStatus } from "@/lib/purchasing";

import { ApproveButton, DraftEditor, EndOrderButton, ReceiveButton, ReturnButton } from "./po-actions";

export const metadata: Metadata = { title: "Purchase order" };

export default function PurchaseOrderPage({ params }: PageProps<"/purchase-orders/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/purchase-orders/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.SUPPLIERS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const po = await apiGet<PurchaseOrder>(`/purchase-orders/${id}`);
  const prefs = me.organisation;
  const c = po.currency_code;
  const st = poStatus(po);
  const caps = po.capabilities;

  return (
    <>
      <PageHeader
        title={po.po_number}
        description={
          <>
            <Link href={`/suppliers/${po.supplier.id}`} className="text-steel hover:underline">
              {po.supplier.name}
            </Link>{" "}
            · {po.branch.name}
          </>
        }
        back={{ href: "/purchase-orders", label: "Purchase orders" }}
        actions={
          <span className="flex items-center gap-2">
            <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
            <PdfLink href={`/purchase-orders/${po.id}/pdf`} />
          </span>
        }
      />
      {po.closed_reason ? (
        <Alert tone="info" className="mb-4">
          {po.status === "cancelled" ? "Cancelled" : "Closed short"}: {po.closed_reason}
        </Alert>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-5">
          <Panel title={caps.edit ? "Lines" : "Order"} flush={!caps.edit}>
            {caps.edit ? (
              <DraftEditor key={po.version} po={po} />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-sm">
                  <thead className="border-b border-border text-xs text-muted">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Part</th>
                      <th className="px-4 py-2 text-right font-medium">Ordered</th>
                      <th className="px-4 py-2 text-right font-medium">Received</th>
                      <th className="px-4 py-2 text-right font-medium">Outstanding</th>
                      <th className="px-4 py-2 text-right font-medium">Unit cost</th>
                      <th className="px-4 py-2 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {po.lines.map((l) => (
                      <tr key={l.id}>
                        <td className="px-4 py-2">
                          <Link href={`/inventory/parts/${l.part.id}`} className="font-mono text-steel hover:underline">
                            {l.sku}
                          </Link>{" "}
                          {l.part.name}
                          {l.supplier_sku ? <span className="block font-mono text-xs text-muted">{l.supplier_sku}</span> : null}
                          {Number(l.quantity_returned) ? <span className="block text-xs text-muted">{qty(l.quantity_returned)} returned</span> : null}
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{qty(l.quantity_ordered)}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{qty(l.quantity_received)}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{qty(l.outstanding)}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{formatMoney(l.unit_cost, c)}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{formatMoney(l.line_total, c)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {caps.approve || caps.receive || caps.return_goods || caps.cancel || caps.close ? (
            <section aria-label="Actions" className="flex flex-wrap gap-2 rounded-panel border border-border bg-surface p-4">
              {caps.approve ? <ApproveButton po={po} /> : null}
              {caps.receive ? <ReceiveButton po={po} /> : null}
              {caps.return_goods ? <ReturnButton po={po} /> : null}
              {caps.close ? <EndOrderButton po={po} mode="close" /> : null}
              {caps.cancel ? <EndOrderButton po={po} mode="cancel" /> : null}
            </section>
          ) : null}

          {po.receipts.length ? (
            <Panel title="Deliveries received" flush>
              <ul className="divide-y divide-border">
                {po.receipts.map((g) => (
                  <li key={g.id} className="px-4 py-3 text-sm">
                    <div className="flex justify-between gap-3">
                      <span>
                        <span className="font-mono">{g.grn_number}</span> into {g.location.name}
                        <span className="block text-xs text-muted">
                          {formatDateTime(g.received_at, prefs)} · {g.received_by}
                          {g.delivery_reference ? ` · delivery note ${g.delivery_reference}` : ""}
                          {g.supplier_invoice_reference ? ` · invoice ${g.supplier_invoice_reference}` : ""}
                        </span>
                      </span>
                      <span className="font-mono whitespace-nowrap tabular-nums">{formatMoney(g.total, c)}</span>
                    </div>
                    <ul className="mt-1 text-xs text-muted">
                      {g.lines.map((x, i) => (
                        <li key={i}>
                          {qty(x.quantity)} × <span className="font-mono">{x.sku}</span>
                          {x.discrepancy ? <span className="text-status-danger"> · {x.discrepancy}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          {po.returns.length ? (
            <Panel title="Returned to supplier" flush>
              <ul className="divide-y divide-border">
                {po.returns.map((r) => (
                  <li key={r.id} className="flex justify-between gap-3 px-4 py-3 text-sm">
                    <span>
                      {r.lines.map((x) => `${qty(x.quantity)} × ${x.sku}`).join(", ")} from {r.location.name}
                      <span className="block text-xs text-muted">
                        {formatDateTime(r.created_at, prefs)} · {r.created_by} · {r.reason}
                        {r.reference ? ` · ${r.reference}` : ""}
                      </span>
                    </span>
                    <span className="font-mono whitespace-nowrap tabular-nums">{formatMoney(r.total, c)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </div>

        <div className="space-y-5">
          <Panel title="Summary">
            <dl className="space-y-1.5 text-sm">
              <Row label="Order total (excl. tax)" value={formatMoney(po.total, c)} />
              <Row label="Received" value={formatMoney(po.received_value, c)} />
              {Number(po.returned_value) ? <Row label="Returned" value={formatMoney(po.returned_value, c)} /> : null}
            </dl>
          </Panel>
          <Panel title="Details">
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-xs text-muted">Required by</dt>
                <dd>
                  {po.expected_date ? formatDate(po.expected_date, prefs) : "—"}
                  {po.is_overdue ? <span className="ml-2 text-status-danger">Overdue</span> : null}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Prepared by</dt>
                <dd>
                  {po.created_by}, {formatDate(po.created_at, prefs)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Approved</dt>
                <dd>{po.approved_at ? `${po.approved_by}, ${formatDate(po.approved_at, prefs)}` : "Not yet"}</dd>
              </div>
            </dl>
            {po.notes && !caps.edit ? <p className="mt-3 text-sm whitespace-pre-line">{po.notes}</p> : null}
          </Panel>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono tabular-nums">{value}</dd>
    </div>
  );
}
