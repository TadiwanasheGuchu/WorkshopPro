"use client";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="max-w-xl space-y-4">
      <Alert tone="error" title="This page could not be loaded">
        Try again. If the problem continues, contact your administrator.
        {error.digest ? <span className="mt-1 block font-mono text-xs">Reference: {error.digest}</span> : null}
      </Alert>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
