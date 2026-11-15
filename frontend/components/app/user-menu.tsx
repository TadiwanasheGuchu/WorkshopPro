"use client";

import { ChevronDown, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { DropdownMenu } from "radix-ui";

import { api } from "@/lib/api/client";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function UserMenu({ fullName, email }: { fullName: string; email: string }) {
  async function signOut() {
    try {
      await api("POST", "/auth/logout");
    } finally {
      // Full page load on sign-out: discards all client-side state and cached pages.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/sign-in");
    }
  }

  const item =
    "flex cursor-default items-center gap-2 rounded-control px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-mist";

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="flex items-center gap-2 rounded-control px-1.5 py-1 hover:bg-mist"
        aria-label={`Account menu for ${fullName}`}
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-steel text-xs font-semibold text-white">
          {initials(fullName)}
        </span>
        <span className="hidden text-sm font-medium md:inline">{fullName}</span>
        <ChevronDown className="hidden size-4 text-muted md:inline" aria-hidden />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 min-w-56 rounded-panel border border-border bg-surface p-1 shadow-lg"
        >
          <div className="px-2.5 py-2">
            <p className="text-sm font-medium">{fullName}</p>
            <p className="text-xs text-muted">{email}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item asChild className={item}>
            <Link href="/account">
              <UserRound className="size-4" aria-hidden /> Account and password
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item className={item} onSelect={() => void signOut()}>
            <LogOut className="size-4" aria-hidden /> Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
