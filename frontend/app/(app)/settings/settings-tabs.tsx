"use client";

import { usePathname } from "next/navigation";

import { TabNav } from "@/components/ui/page";

const TABS = [
  { href: "/settings", label: "Organisation" },
  { href: "/settings/tax-rates", label: "Tax rates" },
  { href: "/settings/numbering", label: "Numbering" },
  { href: "/settings/inspection-templates", label: "Inspection checklists" },
  { href: "/settings/system", label: "System status" },
];

export function SettingsTabs() {
  const pathname = usePathname();
  const active = TABS.map((t) => t.href).filter((h) => pathname === h || pathname.startsWith(`${h}/`)).sort((a, b) => b.length - a.length)[0] ?? pathname;
  return <TabNav tabs={TABS} active={active} />;
}
