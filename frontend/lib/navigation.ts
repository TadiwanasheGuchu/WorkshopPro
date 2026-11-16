import type { Me } from "./api/types";
import { P, can, canInAnyBranch } from "./permissions";

export type NavIcon = "dashboard" | "users" | "branches" | "settings" | "audit" | "customers" | "vehicles" | "job_cards" | "appointments" | "quotations" | "invoices" | "payments" | "reports" | "parts" | "movements" | "locations" | "suppliers" | "purchase_orders";

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
  const workshop: NavItem[] = [];
  if (canInAnyBranch(me, P.JOB_CARDS_VIEW) || canInAnyBranch(me, P.JOB_CARDS_WORK)) {
    workshop.push({ href: "/job-cards", label: "Job cards", icon: "job_cards", match: ["/inspections"] });
  }
  if (canInAnyBranch(me, P.APPOINTMENTS_VIEW)) {
    workshop.push({ href: "/appointments", label: "Appointments", icon: "appointments" });
  }
  if (workshop.length) groups.push({ label: "Workshop", items: workshop });
  if (customers.length) groups.push({ label: "Customers", items: customers });
  const inventory: NavItem[] = [];
  if (canInAnyBranch(me, P.INVENTORY_VIEW)) {
    inventory.push(
      { href: "/inventory/parts", label: "Parts catalogue", icon: "parts" },
      { href: "/inventory/movements", label: "Stock movements", icon: "movements" },
      { href: "/inventory/locations", label: "Stock locations", icon: "locations" },
    );
  }
  if (canInAnyBranch(me, P.SUPPLIERS_VIEW)) {
    inventory.push(
      { href: "/suppliers", label: "Suppliers", icon: "suppliers" },
      { href: "/purchase-orders", label: "Purchase orders", icon: "purchase_orders" },
    );
  }
  if (inventory.length) groups.push({ label: "Inventory", items: inventory });
  const finance: NavItem[] = [];
  if (canInAnyBranch(me, P.QUOTATIONS_VIEW)) finance.push({ href: "/quotations", label: "Quotations", icon: "quotations" });
  if (canInAnyBranch(me, P.INVOICES_VIEW)) {
    finance.push({ href: "/invoices", label: "Invoices", icon: "invoices" });
    finance.push({ href: "/payments", label: "Payments", icon: "payments" });
  }
  if (finance.length) groups.push({ label: "Finance", items: finance });
  if (canInAnyBranch(me, P.REPORTS_FINANCIAL) || canInAnyBranch(me, P.REPORTS_OPERATIONAL) || canInAnyBranch(me, P.REPORTS_INVENTORY)) {
    groups.push({ label: "Analytics", items: [{ href: "/reports", label: "Reports", icon: "reports" }] });
  }
  if (admin.length) groups.push({ label: "Administration", items: admin });
  return groups;
}
