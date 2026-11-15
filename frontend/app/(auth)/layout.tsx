import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="bg-slate-deep">
        <div className="mx-auto flex h-12 max-w-md items-center px-4">
          <span className="text-sm font-semibold tracking-wide text-white">WORKSHOPPRO</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-md flex-1 px-4 py-8 sm:py-12">
        <div className="rounded-panel border border-border bg-surface p-5 sm:p-6">{children}</div>
      </main>
    </div>
  );
}
