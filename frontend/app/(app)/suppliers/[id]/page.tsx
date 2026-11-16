import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { DetailList, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, PoListItem, Supplier } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { P, can, canInAnyBranch } from "@/lib/permissions";
import { poStatus } from "@/lib/purchasing";

import { ArchiveSupplierButton, NewOrderButton, RemoveSupplierPartButton, SupplierPartButton } from "./supplier-actions";

export const metadata: Metadata = { title: "Supplier" };

export default function SupplierPage({ params }: PageProps<"/suppliers/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} />
    </Suspense>
  );
}

async function Content({ params }: { params: PageProps<"/suppliers/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.SUPPLIERS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const [s, orders] = await Promise.all([
    apiGet<Supplier>(`/suppliers/${id}`),
    apiGet<Page<PoListItem>>(`/purchase-orders${query({ supplier_id: id, page_size: 10 })}`),
  ]);
  const prefs = me.organisation;
  const c = prefs.currency_code;
  const orderBranches = me.branches.filter((b) => can(me, P.PURCHASING_MANAGE, b.id));
  const edit = s.capabilities.edit;

  return (
    <>
      <PageHeader
        title={s.name}
        back={{ href: "/suppliers", label: "Suppliers" }}
        actions={
          <span className="flex flex-wrap items-center gap-2">
            {s.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
            {edit ? (
              <Button asChild>
                <Link href={`/suppliers/${s.id}/edit`}>Edit</Link>
              </Button>
            ) : null}
            {s.capabilities.archive ? <ArchiveSupplierButton supplier={s} /> : null}
            {!s.archived_at && orderBranches.length ? <NewOrderButton supplierId={s.id} branches={orderBranches} /> : null}
          </span>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-5">
          <Panel title="Part codes and prices" flush actions={edit ? <SupplierPartButton supplierId={s.id} /> : null}>
            {s.parts.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">No part codes yet. Prices are filled in automatically when goods are received.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] text-sm">
                  <thead className="border-b border-border text-xs text-muted">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Our part</th>
                      <th className="px-4 py-2 text-left font-medium">Their code</th>
                      <th className="px-4 py-2 text-right font-medium">Last price</th>
                      <th className="px-4 py-2 text-right font-medium">Lead time</th>
                      {edit ? <th className="px-4 py-2" /> : null}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {s.parts.map((p) => (
                      <tr key={p.part.id}>
                        <td className="px-4 py-2">
                          <Link href={`/inventory/parts/${p.part.id}`} className="font-mono text-steel hover:underline">
                            {p.sku}
                          </Link>{" "}
                          {p.part.name}
                        </td>
                        <td className="px-4 py-2 font-mono">{p.supplier_sku ?? "—"}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">{p.last_cost ? formatMoney(p.last_cost, c) : "—"}</td>
                        <td className="px-4 py-2 text-right">{p.lead_time_days != null ? `${p.lead_time_days} days` : "—"}</td>
                        {edit ? (
                          <td className="px-4 py-2 text-right whitespace-nowrap">
                            <SupplierPartButton supplierId={s.id} existing={p} />
                            <RemoveSupplierPartButton supplierId={s.id} part={p} />
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <Panel
            title="Recent purchase orders"
            flush
            actions={
              orders.total > orders.items.length ? (
                <Link href={`/purchase-orders?supplier=${s.id}`} className="text-sm text-steel hover:underline">
                  All {orders.total}
                </Link>
              ) : null
            }
          >
            {orders.items.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">No orders yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {orders.items.map((o) => {
                  const st = poStatus(o);
                  return (
                    <li key={o.id}>
                      <Link href={`/purchase-orders/${o.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-mist">
                        <span>
                          <span className="font-mono text-steel">{o.po_number}</span>
                          <span className="block text-xs text-muted">
                            {o.branch.name} · {formatDate(o.created_at, prefs)}
                          </span>
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="font-mono tabular-nums">{formatMoney(o.total, o.currency_code)}</span>
                          <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>
        <Panel title="Details">
          <DetailList
            items={[
              { label: "Contact", value: s.contact_person },
              { label: "Phone", value: s.phone },
              { label: "Email", value: s.email },
              { label: "Our account number", value: s.account_number ? <span className="font-mono">{s.account_number}</span> : null },
              { label: "Tax number", value: s.tax_number },
              { label: "Payment terms", value: `${s.payment_terms_days} days` },
              { label: "Received, last 90 days", value: <span className="font-mono">{formatMoney(s.received_value_90_days, c)}</span> },
            ]}
          />
          {s.address ? <p className="mt-4 text-sm whitespace-pre-line">{s.address}</p> : null}
          {s.notes ? <p className="mt-4 text-sm whitespace-pre-line text-muted">{s.notes}</p> : null}
        </Panel>
      </div>
    </>
  );
}
