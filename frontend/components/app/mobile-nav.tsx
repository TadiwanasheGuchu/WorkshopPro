"use client";

import { Menu, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";

import type { NavGroup } from "@/lib/navigation";

import { SidebarNav } from "./sidebar-nav";

export function MobileNav({ groups, organisationName }: { groups: NavGroup[]; organisationName: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="-ml-2 inline-flex size-10 items-center justify-center rounded-control hover:bg-mist lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="size-5" aria-hidden />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-deep/40 lg:hidden" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] overflow-y-auto bg-slate-deep p-3 focus:outline-none lg:hidden">
          <div className="mb-4 flex items-center justify-between px-3 pt-1">
            <div>
              <Dialog.Title className="text-sm font-semibold tracking-wide text-white">
                WORKSHOPPRO
              </Dialog.Title>
              <Dialog.Description className="text-xs text-white/60">{organisationName}</Dialog.Description>
            </div>
            <Dialog.Close
              className="inline-flex size-10 items-center justify-center rounded-control text-white hover:bg-white/10"
              aria-label="Close navigation"
            >
              <X className="size-5" aria-hidden />
            </Dialog.Close>
          </div>
          <SidebarNav groups={groups} onNavigate={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
