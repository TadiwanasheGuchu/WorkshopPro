import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton, TabNav } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { NotificationEntry, NotificationStatus, Page } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { CHANNEL_LABEL, NOTIFICATION_STATUS } from "@/lib/notifications";
import { P, canInAnyBranch } from "@/lib/permissions";

import { RetryButton } from "./notification-actions";

export const metadata: Metadata = { title: "Notifications" };

const FILTERS: { key: NotificationStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "failed", label: "Failed" },
  { key: "skipped", label: "Not sent" },
  { key: "queued", label: "Sending" },
];

export default function NotificationsPage({ searchParams }: PageProps<"/notifications">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={10} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/notifications">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.NOTIFICATIONS_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const status = FILTERS.find((f) => f.key === params.status && f.key !== "all")?.key;
  const customer = typeof params.customer === "string" && /^[0-9a-f-]{36}$/.test(params.customer) ? params.customer : undefined;
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<NotificationEntry>>(`/notifications${query({ status, customer_id: customer, page, page_size: 25 })}`);
  const prefs = me.organisation;

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Messages sent to customers by WhatsApp or email, and their delivery status."
        actions={
          <Link href="/notifications/templates" className="text-sm text-steel hover:underline">
            Message templates
          </Link>
        }
      />
      <TabNav tabs={FILTERS.map((f) => ({ href: `/notifications${query({ status: f.key === "all" ? undefined : f.key, customer })}`, label: f.label }))} active={`/notifications${query({ status, customer })}`} />
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={status === "failed" ? "No failed messages" : "No notifications"} />
        ) : (
          <ul className="divide-y divide-border">
            {data.items.map((n) => {
              const st = NOTIFICATION_STATUS[n.status];
              return (
                <li key={n.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-start">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium">{n.event_label}</span>
                      <span className="text-muted">·</span>
                      <Link href={`/customers/${n.customer.id}`} className="text-steel hover:underline">
                        {n.customer.name}
                      </Link>
                      <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                    </p>
                    <p className="text-xs text-muted">
                      {formatDateTime(n.created_at, prefs)}
                      {n.channel !== "none" ? ` · ${CHANNEL_LABEL[n.channel]} to ${n.recipient}` : ""}
                      {n.attempts > 1 ? ` · ${n.attempts} attempts` : ""}
                    </p>
                    {n.skip_reason ? <p className="mt-1 text-sm">{n.skip_reason}</p> : null}
                    {n.last_error && n.status !== "sent" && n.status !== "delivered" && n.status !== "read" ? <p className="mt-1 text-sm text-status-danger">{n.last_error}</p> : null}
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-steel">Message</summary>
                      {n.subject ? <p className="mt-1 text-sm font-medium">{n.subject}</p> : null}
                      <p className="mt-1 text-sm whitespace-pre-line text-muted">{n.body}</p>
                    </details>
                  </div>
                  {n.can_retry ? <RetryButton id={n.id} /> : null}
                </li>
              );
            })}
          </ul>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(p) => `/notifications${query({ status, customer, page: p })}`} />
        </div>
      </Panel>
    </>
  );
}
