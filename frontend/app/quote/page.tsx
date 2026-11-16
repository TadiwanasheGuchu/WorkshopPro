import type { Metadata } from "next";

import { QuoteView } from "./quote-view";

export const metadata: Metadata = { title: "Your quotation", robots: { index: false, follow: false } };

export default function PublicQuotePage() {
  return (
    <div className="min-h-full">
      <header className="bg-slate-deep">
        <div className="mx-auto flex h-12 max-w-2xl items-center px-4">
          <span className="text-sm font-semibold tracking-wide text-white">Quotation</span>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-4 py-6">
        <QuoteView />
      </main>
    </div>
  );
}
