import type { Me } from "./api/types";
import { P, can, canInAnyBranch } from "./permissions";

export type NavIcon = "dashboard" | "users" | "branches" | "settings" | "audit" | "customers" | "vehicles";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIcon;
  /** Other path prefixes that should highlight this item. */
  match?: string[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/**
 * Sidebar structure from CLAUDE.md §9. Items appear only when the user has access and
 * the module exists; workshop, customer, inventory and finance groups arrive with
 * their phases.
 */
export function navigationFor(me: Me): NavGroup[] {
  const admin: NavItem[] = [];
  if (can(me, P.USERS_VIEW)) {
    admin.push({ href: "/users", label: "Users & roles", icon: "users", match: ["/roles"] });
  }
  if (canInAnyBranch(me, P.BRANCHES_VIEW)) {
    admin.push({ href: "/branches", label: "Branches", icon: "branches" });
  }
  if (can(me, P.SETTINGS_VIEW)) {
    admin.push({ href: "/settings", label: "Settings", icon: "settings" });
  }
  if (can(me, P.AUDIT_VIEW)) {
    admin.push({ href: "/audit-logs", label: "Audit log", icon: "audit" });
  }

  const customers: NavItem[] = [];
  if (canInAnyBranch(me, P.CUSTOMERS_VIEW)) customers.push({ href: "/customers", label: "Customers", icon: "customers" });
  if (canInAnyBranch(me, P.VEHICLES_VIEW)) customers.push({ href: "/vehicles", label: "Vehicles", icon: "vehicles" });

  const groups: NavGroup[] = [
    { label: "Overview", items: [{ href: "/", label: "Dashboard", icon: "dashboard" }] },
  ];
  if (customers.length) groups.push({ label: "Customers", items: customers });
  if (admin.length) groups.push({ label: "Administration", items: admin });
  return groups;
}
