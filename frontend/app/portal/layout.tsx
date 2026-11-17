import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: { template: "%s · Customer portal", default: "Customer portal" }, robots: { index: false, follow: false } };

export default function PortalLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-full bg-mist">{children}</div>;
}
