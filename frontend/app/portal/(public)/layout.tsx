import type { ReactNode } from "react";

export default function PortalPublicLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="bg-slate-deep">
        <div className="mx-auto flex h-12 max-w-3xl items-center px-4">
          <span className="text-sm font-semibold tracking-wide text-white">Customer portal</span>
        </div>
      </header>
      <main className="mx-auto max-w-md px-4 py-8">{children}</main>
    </>
  );
}
