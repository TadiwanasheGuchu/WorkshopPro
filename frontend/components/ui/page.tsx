import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <div className="mb-5">
      {back ? (
        <Link href={back.href} className="mb-1 inline-block text-sm text-steel hover:underline">
          ← {back.label}
        </Link>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">{title}</h1>
          {description ? <p className="mt-0.5 text-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}

/** A titled section of a page: white panel with a header row. */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  flush = false,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Remove body padding (for tables and lists). */
  flush?: boolean;
}) {
  return (
    <section className={cn("rounded-panel border border-border bg-surface", className)}>
      {title ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <h2 className="font-semibold">{title}</h2>
            {description ? <p className="text-xs text-muted">{description}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      <div className={flush ? undefined : "p-4"}>{children}</div>
    </section>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children ? <div className="mt-1 text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export function TabNav({ tabs, active }: { tabs: { href: string; label: string }[]; active: string }) {
  return (
    <nav aria-label="Section" className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((tab) => {
        const current = tab.href === active;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap",
              current ? "border-steel text-slate-deep" : "border-transparent text-muted hover:text-slate-deep",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  hrefFor,
}: {
  page: number;
  pageSize: number;
  total: number;
  hrefFor: (page: number) => string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  const link = "rounded-control border border-border bg-surface px-3 py-1.5 text-sm hover:bg-mist";
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
      <span className="text-muted tabular-nums">
        {from}–{to} of {total}
      </span>
      <span className="flex gap-2">
        {page > 1 ? (
          <Link className={link} href={hrefFor(page - 1)}>
            Previous
          </Link>
        ) : null}
        {page < pages ? (
          <Link className={link} href={hrefFor(page + 1)}>
            Next
          </Link>
        ) : null}
      </span>
    </nav>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-control bg-mist", className)} />;
}

export function PanelSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="rounded-panel border border-border bg-surface p-4" aria-busy="true" aria-label="Loading">
      <div className="space-y-3">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    </div>
  );
}

/** Definition list for read-only record details. */
export function DetailList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="text-xs text-muted">{item.label}</dt>
          <dd className="mt-0.5">{item.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function NoAccess() {
  return (
    <div className="max-w-xl rounded-panel border border-border bg-surface p-5">
      <h2 className="font-semibold">You do not have access to this page</h2>
      <p className="mt-1 text-muted">Ask your workshop administrator if you need access.</p>
    </div>
  );
}
