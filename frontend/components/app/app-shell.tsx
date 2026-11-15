import { cookies } from "next/headers";
import type { ReactNode } from "react";

import type { Me } from "@/lib/api/types";
import { navigationFor } from "@/lib/navigation";

import { BRANCH_COOKIE } from "@/lib/constants";

import { BranchSwitcher } from "./branch-switcher";
import { MobileNav } from "./mobile-nav";
import { SidebarNav } from "./sidebar-nav";
import { UserMenu } from "./user-menu";

export async function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const groups = navigationFor(me);
  const selectedBranch = (await cookies()).get(BRANCH_COOKIE)?.value ?? null;
  const allowAll = me.branches.length > 1;

  return (
    <div className="min-h-full lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="hidden bg-slate-deep lg:block">
        <div className="sticky top-0 flex h-screen flex-col overflow-y-auto p-3">
          <div className="mb-5 px-3 pt-2">
            <p className="text-sm font-semibold tracking-wide text-white">WORKSHOPPRO</p>
            <p className="truncate text-xs text-white/60">{me.organisation.name}</p>
          </div>
          <SidebarNav groups={groups} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface px-4">
          <MobileNav groups={groups} organisationName={me.organisation.name} />
          <span className="font-semibold lg:hidden">WorkshopPro</span>
          <div className="ml-auto flex items-center gap-3">
            <BranchSwitcher branches={me.branches} selected={selectedBranch} allowAll={allowAll} />
            <UserMenu fullName={me.full_name} email={me.email} />
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-5 lg:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}

export function AppShellSkeleton() {
  return (
    <div className="min-h-full lg:grid lg:grid-cols-[15rem_1fr]" aria-busy="true">
      <aside className="hidden bg-slate-deep lg:block" />
      <div>
        <header className="h-14 border-b border-border bg-surface" />
      </div>
    </div>
  );
}
