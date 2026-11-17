import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuditList } from "@/components/app/audit-list";
import { JobHistory } from "@/components/app/job-history";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { DetailList, EmptyState, NoAccess, PageHeader, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet } from "@/lib/api/server";
import type { AuditLogEntry, CustomerBalance, CustomerDetail, JobCardSummary, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import { CONSENT_CHANNEL, CONSENT_METHOD, CONTACT_METHOD, formatPhone, vehicleTitle } from "@/lib/labels";
import { P, can, canInAnyBranch } from "@/lib/permissions";

import { ArchiveCustomerButton, RecordConsentButton } from "./customer-actions";

export const metadata: Metadata = { title: "Customer" };

export default function CustomerPage({ params }: PageProps<"/customers/[id]">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content params={params} />
    </Suspense>
  );
}

const CHANNELS = ["whatsapp", "sms", "email", "marketing"] as const;

async function Content({ params }: { params: PageProps<"/customers/[id]">["params"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.CUSTOMERS_VIEW)) return <NoAccess />;
  const { id } = await params;
  const [c, activity] = await Promise.all([
    apiGet<CustomerDetail>(`/customers/${id}`),
    can(me, P.AUDIT_VIEW)
      ? apiGet<Page<AuditLogEntry>>(`/audit-logs?entity_type=customer&entity_id=${id}&page_size=8`)
      : Promise.resolve(null),
  ]);
  const jobs = canInAnyBranch(me, P.JOB_CARDS_VIEW) ? await apiGet<Page<JobCardSummary>>(`/job-cards?customer_id=${id}&page_size=20`) : null;
  const balance = canInAnyBranch(me, P.INVOICES_VIEW) ? await apiGet<CustomerBalance>(`/customers/${id}/balance`) : null;
  const manage = canInAnyBranch(me, P.CUSTOMERS_MANAGE);
  const manageVehicles = canInAnyBranch(me, P.VEHICLES_MANAGE);
  const prefs = me.organisation;
  const phones = c.contacts.filter((x) => x.kind === "phone");
  const emails = c.contacts.filter((x) => x.kind === "email");
  const physical = c.addresses.find((a) => a.kind === "physical");

  return (
    <>
      <PageHeader
        title={c.display_name}
        description={c.customer_type === "company" ? `Company${c.contact_person ? ` · ${c.contact_person}` : ""}` : undefined}
        back={{ href: "/customers", label: "Customers" }}
        actions={
          <>
            {c.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
            {manage && !c.archived_at ? (
              <Button asChild>
                <Link href={`/customers/${c.id}/edit`}>Edit</Link>
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          {balance ? (
            <Panel title="Account" flush>
              <dl className="space-y-1.5 px-4 py-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Outstanding</dt>
                  <dd className="font-mono tabular-nums">{formatMoney(balance.outstanding, balance.currency_code)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Unapplied credit</dt>
                  <dd className="font-mono tabular-nums">{formatMoney(balance.unallocated_credit, balance.currency_code)}</dd>
                </div>
              </dl>
              {balance.open_invoices.length ? (
                <ul className="divide-y divide-border border-t border-border">
                  {balance.open_invoices.map((i) => (
                    <li key={i.id}>
                      <Link href={`/invoices/${i.id}`} className="flex justify-between gap-2 px-4 py-2 text-sm hover:bg-mist">
                        <span className="font-mono text-steel">{i.invoice_number}</span>
                        <span className={i.is_overdue ? "font-mono text-status-danger tabular-nums" : "font-mono tabular-nums"}>
                          {formatMoney(i.balance_due, i.currency_code)}
                          {i.is_overdue ? " overdue" : ""}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="border-t border-border px-4 py-2 text-xs text-muted">Outstanding is the unpaid balance of issued invoices. Unapplied credit is money received but not yet applied to an invoice.</p>
            </Panel>
          ) : null}
          {canInAnyBranch(me, P.NOTIFICATIONS_VIEW) ? (
            <Link href={`/notifications?customer=${c.id}`} className="block text-sm text-steel hover:underline">
              Messages sent to this customer
            </Link>
          ) : null}
          <Panel title="Contact">
            <DetailList
              items={[
                {
                  label: "Phone",
                  value: phones.length ? (
                    <ul>
                      {phones.map((p) => (
                        <li key={p.id}>
                          <a href={`tel:${p.value}`} className="font-mono text-steel hover:underline">
                            {formatPhone(p.value)}
                          </a>
                          {p.label ? <span className="text-muted"> · {p.label}</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null,
                },
                {
                  label: "Email",
                  value: emails.length ? (
                    <ul>
                      {emails.map((e) => (
                        <li key={e.id}>
                          <a href={`mailto:${e.value}`} className="text-steel hover:underline">
                            {e.value}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null,
                },
                { label: "Prefers", value: CONTACT_METHOD[c.preferred_contact_method] },
                {
                  label: "Address",
                  value: physical ? [physical.line1, physical.line2, physical.city, physical.postal_code].filter(Boolean).join(", ") : null,
                },
                ...(c.tax_number ? [{ label: "Tax / VAT number", value: c.tax_number }] : []),
                ...(c.registration_number ? [{ label: "Company registration", value: c.registration_number }] : []),
              ]}
            />
            {c.notes ? <p className="mt-4 border-t border-border pt-3 text-sm whitespace-pre-line">{c.notes}</p> : null}
          </Panel>

          <Panel
            title="Vehicles"
            flush
            actions={
              manageVehicles && !c.archived_at ? (
                <Button asChild size="sm" variant="primary">
                  <Link href={`/vehicles/new?customer_id=${c.id}`}>Add vehicle</Link>
                </Button>
              ) : null
            }
          >
            {c.vehicles.length === 0 ? (
              <EmptyState title="No vehicles registered" />
            ) : (
              <ul className="divide-y divide-border">
                {c.vehicles.map((v) => (
                  <li key={v.id}>
                    <Link href={`/vehicles/${v.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-mist">
                      <span className="font-mono font-medium text-steel">{vehicleTitle(v)}</span>
                      <span className="flex items-center gap-2 text-sm text-muted">
                        {[v.year, v.make, v.model].filter(Boolean).join(" ")}
                        {v.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {jobs ? (
            <Panel title="Job history" flush>
              <JobHistory jobs={jobs.items} me={me} showVehicle />
            </Panel>
          ) : null}
        </div>

        <div className="space-y-5">
          <Panel
            title="Communication consent"
            flush
            actions={manage && !c.archived_at ? <RecordConsentButton customerId={c.id} /> : null}
          >
            <ul className="divide-y divide-border">
              {CHANNELS.map((channel) => {
                const consent = c.consents.find((x) => x.channel === channel);
                return (
                  <li key={channel} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm">{CONSENT_CHANNEL[channel]}</span>
                      {consent ? (
                        <StatusBadge tone={consent.status === "granted" ? "success" : "danger"}>
                          {consent.status === "granted" ? "Agreed" : "Withdrawn"}
                        </StatusBadge>
                      ) : (
                        <StatusBadge tone="neutral">Not recorded</StatusBadge>
                      )}
                    </div>
                    {consent ? (
                      <p className="mt-0.5 text-xs text-muted">
                        {CONSENT_METHOD[consent.method]} · {formatDate(consent.recorded_at, prefs)}
                        {consent.recorded_by ? ` · ${consent.recorded_by}` : ""}
                        {consent.evidence ? ` · ${consent.evidence}` : ""}
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Panel>

          {activity ? (
            <Panel title="Recent activity" flush>
              <AuditList entries={activity.items} me={me} />
            </Panel>
          ) : null}

          {manage ? (
            <Panel title="Archive">
              <ArchiveCustomerButton customerId={c.id} archived={Boolean(c.archived_at)} name={c.display_name} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
