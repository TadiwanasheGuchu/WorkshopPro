import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { EmptyState, NoAccess, PageHeader, Pagination, Panel, PanelSkeleton } from "@/components/ui/page";
import { apiGet, query } from "@/lib/api/server";
import type { Page, Vehicle } from "@/lib/api/types";
import { requireMe } from "@/lib/auth";
import { formatKm, vehicleTitle } from "@/lib/labels";
import { P, canInAnyBranch } from "@/lib/permissions";

export const metadata: Metadata = { title: "Vehicles" };

export default function VehiclesPage({ searchParams }: PageProps<"/vehicles">) {
  return (
    <Suspense fallback={<PanelSkeleton rows={8} />}>
      <Content searchParams={searchParams} />
    </Suspense>
  );
}

async function Content({ searchParams }: { searchParams: PageProps<"/vehicles">["searchParams"] }) {
  const me = await requireMe();
  if (!canInAnyBranch(me, P.VEHICLES_VIEW)) return <NoAccess />;
  const params = await searchParams;
  const search = typeof params.search === "string" ? params.search.slice(0, 100) : "";
  const page = Math.max(1, Number(params.page) || 1);
  const data = await apiGet<Page<Vehicle>>(`/vehicles${query({ search, page, page_size: 25 })}`);

  return (
    <>
      <PageHeader
        title="Vehicles"
        actions={
          canInAnyBranch(me, P.VEHICLES_MANAGE) ? (
            <Button asChild variant="primary">
              <Link href="/vehicles/new">Register vehicle</Link>
            </Button>
          ) : null
        }
      />
      <form method="get" role="search" className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="vehicle-search" className="sr-only">
          Search vehicles
        </label>
        <Input id="vehicle-search" name="search" type="search" defaultValue={search} placeholder="Registration, VIN, make or model" className="sm:max-w-sm" />
        <Button type="submit">Search</Button>
      </form>
      <Panel flush>
        {data.items.length === 0 ? (
          <EmptyState title={search ? `No vehicles match "${search}"` : "No vehicles yet"} />
        ) : (
          <>
            <table className="hidden w-full text-left md:table">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Registration</th>
                  <th className="px-4 py-2.5 font-medium">Vehicle</th>
                  <th className="px-4 py-2.5 font-medium">Owner</th>
                  <th className="px-4 py-2.5 text-right font-medium">Odometer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.items.map((v) => (
                  <tr key={v.id} className="hover:bg-mist">
                    <td className="px-4 py-3">
                      <Link href={`/vehicles/${v.id}`} className="font-mono font-medium text-steel hover:underline">
                        {vehicleTitle(v)}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm">{[v.year, v.make, v.model, v.variant].filter(Boolean).join(" ")}</td>
                    <td className="px-4 py-3 text-sm">
                      <Link href={`/customers/${v.customer.id}`} className="hover:underline">
                        {v.customer.display_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm tabular-nums">{formatKm(v.odometer_km)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-border md:hidden">
              {data.items.map((v) => (
                <li key={v.id}>
                  <Link href={`/vehicles/${v.id}`} className="block px-4 py-3 active:bg-mist">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium">{vehicleTitle(v)}</span>
                      {v.archived_at ? <StatusBadge tone="neutral">Archived</StatusBadge> : null}
                    </div>
                    <p className="text-sm text-muted">
                      {[v.year, v.make, v.model].filter(Boolean).join(" ")} · {v.customer.display_name}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="border-t border-border">
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} hrefFor={(p) => `/vehicles${query({ search, page: p })}`} />
        </div>
      </Panel>
    </>
  );
}
