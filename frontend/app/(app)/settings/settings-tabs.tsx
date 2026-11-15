"use client";

import { usePathname } from "next/navigation";

import { TabNav } from "@/components/ui/page";

const TABS = [
  { href: "/settings", label: "Organisation" },
  { href: "/settings/tax-rates", label: "Tax rates" },
  { href: "/settings/numbering", label: "Numbering" },
  { href: "/settings/system", label: "System status" },
];

export function SettingsTabs() {
  return <TabNav tabs={TABS} active={usePathname()} />;
}
