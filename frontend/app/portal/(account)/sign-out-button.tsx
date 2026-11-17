"use client";

import { api } from "@/lib/api/client";

export function SignOutButton() {
  return (
    <button
      type="button"
      className="text-white/90 hover:text-white"
      onClick={async () => {
        await api("POST", "/portal/auth/logout").catch(() => undefined);
        // Full page load: discards all client-side state from the session.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign("/portal/sign-in");
      }}
    >
      Sign out
    </button>
  );
}
