"use client";

import { ArrowLeftRight, Banknote, BarChart3, Bell, Boxes, Building2, CalendarDays, Car, ClipboardList, Contact, FileText, LayoutDashboard, Package, Receipt, ShoppingCart, Truck, ScrollText, Settings, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import type { NavGroup, NavIcon } from "@/lib/navigation";

const icons: Record<NavIcon, LucideIcon> = {
  dashboard: LayoutDashboard,
  users: Users,
  branches: Building2,
  settings: Settings,
  audit: ScrollText,
  customers: Contact,
  vehicles: Car,
  job_cards: ClipboardList,
  appointments: CalendarDays,
  quotations: FileText,
  invoices: Receipt,
  payments: Banknote,
  reports: BarChart3,
  parts: Package,
  movements: ArrowLeftRight,
  locations: Boxes,
  suppliers: Truck,
  purchase_orders: ShoppingCart,
  notifications: Bell,
};

function isActive(pathname: string, href: string, match: string[] = []): boolean {
  if (href === "/") return pathname === "/";
  return [href, ...match].some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function SidebarNav({ groups, onNavigate }: { groups: NavGroup[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="space-y-5">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-1.5 text-[11px] font-semibold tracking-wider text-white/50 uppercase">
            {group.label}
          </p>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = icons[item.icon];
              const active = isActive(pathname, item.href, item.match);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-control px-3 py-2 text-sm",
                      active
                        ? "bg-white/10 font-medium text-white"
                        : "text-white/75 hover:bg-white/5 hover:text-white",
                    )}
                  >
                    <Icon className="size-5 shrink-0" aria-hidden />
                    {item.label}
                    {active ? <span className="ml-auto h-4 w-0.5 rounded-full bg-action" aria-hidden /> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
