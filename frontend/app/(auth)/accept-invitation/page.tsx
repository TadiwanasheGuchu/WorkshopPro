import type { Metadata } from "next";

import { SetPasswordForm } from "@/components/auth/set-password-form";

export const metadata: Metadata = { title: "Activate your account" };

export default function AcceptInvitationPage() {
  return (
    <>
      <h1 className="mb-3 text-lg font-semibold">Activate your account</h1>
      <SetPasswordForm purpose="invitation" />
    </>
  );
}
