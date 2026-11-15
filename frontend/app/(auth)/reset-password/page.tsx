import type { Metadata } from "next";

import { SetPasswordForm } from "@/components/auth/set-password-form";

export const metadata: Metadata = { title: "Choose a new password" };

export default function ResetPasswordPage() {
  return (
    <>
      <h1 className="mb-3 text-lg font-semibold">Choose a new password</h1>
      <SetPasswordForm purpose="password_reset" />
    </>
  );
}
