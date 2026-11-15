import type { Metadata } from "next";
import { Suspense } from "react";

import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in" };

const NOTICES: Record<string, string> = {
  "password-reset": "Your password has been changed. Sign in with your new password.",
  "invitation-accepted": "Your account is ready. Sign in to continue.",
};

export default function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  return (
    <>
      <h1 className="mb-1 text-lg font-semibold">Sign in</h1>
      <p className="mb-5 text-muted">Use the email address your workshop registered for you.</p>
      <Suspense>
        <SignInFormWithParams searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function SignInFormWithParams({ searchParams }: { searchParams: PageProps<"/sign-in">["searchParams"] }) {
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : null;
  const notice = typeof params.notice === "string" ? (NOTICES[params.notice] ?? null) : null;
  return <SignInForm next={next} notice={notice} />;
}
