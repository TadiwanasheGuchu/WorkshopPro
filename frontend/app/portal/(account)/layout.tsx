import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { PanelSkeleton } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { PortalMe } from "@/lib/api/types";

import { SignOutButton } from "./sign-out-button";

export default function PortalAccountLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="bg-slate-deep">
        <div className="mx-auto flex min-h-12 max-w-3xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2">
          <Suspense fallback={<span className="text-sm font-semibold text-white">Customer portal</span>}>
            <Workshop />
          </Suspense>
          <nav aria-label="Portal" className="flex items-center gap-4 text-sm">
            <Link href="/portal" className="text-white/90 hover:text-white">
              Overview
            </Link>
            <Link href="/portal/bookings" className="text-white/90 hover:text-white">
              Bookings
            </Link>
            <Link href="/portal/invoices" className="text-white/90 hover:text-white">
              Invoices
            </Link>
            <Link href="/portal/profile" className="text-white/90 hover:text-white">
              My details
            </Link>
            <SignOutButton />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6">
        <Suspense fallback={<PanelSkeleton rows={6} />}>{children}</Suspense>
      </main>
    </>
  );
}

async function Workshop() {
  const me = await portalGet<PortalMe>("/me");
  return <span className="text-sm font-semibold text-white">{me.organisation_name}</span>;
}
