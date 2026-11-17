import type { Metadata } from "next";

import { RequestLinkForm } from "./request-link-form";

export const metadata: Metadata = { title: "Sign in" };

export default function PortalSignInPage() {
  return (
    <div className="rounded-panel border border-border bg-surface p-5">
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Enter the email address your workshop has on file. We will email you a link to sign in.</p>
      <RequestLinkForm />
    </div>
  );
}
