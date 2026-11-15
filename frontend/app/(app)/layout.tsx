import { Suspense, type ReactNode } from "react";

import { AppShell, AppShellSkeleton } from "@/components/app/app-shell";
import { requireMe } from "@/lib/auth";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<AppShellSkeleton />}>
      <AuthenticatedShell>{children}</AuthenticatedShell>
    </Suspense>
  );
}

async function AuthenticatedShell({ children }: { children: ReactNode }) {
  const me = await requireMe();
  return <AppShell me={me}>{children}</AppShell>;
}
