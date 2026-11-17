import type { Metadata } from "next";

import { ConsumeLink } from "./consume-link";

export const metadata: Metadata = { title: "Signing in" };

export default function PortalAuthPage() {
  return <ConsumeLink />;
}
