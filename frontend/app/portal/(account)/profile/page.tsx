import type { Metadata } from "next";

import { Panel } from "@/components/ui/page";
import { portalGet } from "@/lib/api/server";
import type { PortalMe } from "@/lib/api/types";

import { ProfileForm } from "./profile-form";

export const metadata: Metadata = { title: "My details" };

export default async function PortalProfilePage() {
  const me = await portalGet<PortalMe>("/me");
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">My details</h1>
      <Panel>
        <p className="mb-4 text-sm text-muted">
          Signed in as {me.email}. To change your email address, contact {me.organisation_name}.
        </p>
        <ProfileForm me={me} />
      </Panel>
    </div>
  );
}
