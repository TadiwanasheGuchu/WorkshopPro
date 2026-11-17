"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { api } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

/** The token is in the URL fragment, so it is never sent to servers or logged. */
export function ConsumeLink() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // the link is single use; never try it twice
    started.current = true;
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    history.replaceState(null, "", window.location.pathname);
    const attempt = token
      ? api("POST", "/portal/auth/consume", { token }).then(() => router.replace("/portal"))
      : Promise.reject(new Error("This sign-in link is incomplete."));
    attempt.catch((e) => setError(errorMessage(e)));
  }, [router]);

  return error ? (
    <Alert tone="error" title="Could not sign you in">
      {error}{" "}
      <Link href="/portal/sign-in" className="underline">
        Request a new link
      </Link>
    </Alert>
  ) : (
    <p className="text-sm text-muted">Signing you in…</p>
  );
}
