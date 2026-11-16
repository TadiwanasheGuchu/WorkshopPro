import type { Me } from "./api/types";

/** Permission codes. Must match backend/app/permissions/catalogue.py. */
export const P = {
  SETTINGS_VIEW: "settings.view",
  SETTINGS_MANAGE: "settings.manage",
  BRANCHES_VIEW: "branches.view",
  BRANCHES_MANAGE: "branches.manage",
  USERS_VIEW: "users.view",
  USERS_MANAGE: "users.manage",
  ROLES_MANAGE: "roles.manage",
  AUDIT_VIEW: "audit.view",
  CUSTOMERS_VIEW: "customers.view",
  CUSTOMERS_MANAGE: "customers.manage",
  VEHICLES_VIEW: "vehicles.view",
  VEHICLES_MANAGE: "vehicles.manage",
  JOB_CARDS_VIEW: "job_cards.view",
  JOB_CARDS_CREATE: "job_cards.create",
  JOB_CARDS_MANAGE: "job_cards.manage",
  JOB_CARDS_ASSIGN: "job_cards.assign",
  JOB_CARDS_WORK: "job_cards.work",
  JOB_CARDS_AUTHORISE_EXCEPTION: "job_cards.authorise_exception",
  INSPECTIONS_PERFORM: "inspections.perform",
  INSPECTIONS_AMEND: "inspections.amend",
  INSPECTION_TEMPLATES_MANAGE: "inspection_templates.manage",
  APPOINTMENTS_VIEW: "appointments.view",
  APPOINTMENTS_MANAGE: "appointments.manage",
  QUOTATIONS_VIEW: "quotations.view",
  QUOTATIONS_MANAGE: "quotations.manage",
  QUOTATIONS_RECORD_DECISION: "quotations.record_decision",
  INVOICES_VIEW: "invoices.view",
  INVOICES_MANAGE: "invoices.manage",
  INVOICES_CREDIT: "invoices.credit",
  PAYMENTS_RECORD: "payments.record",
  PAYMENTS_REFUND: "payments.refund",
  REPORTS_OPERATIONAL: "reports.operational",
  REPORTS_FINANCIAL: "reports.financial",
  REPORTS_INVENTORY: "reports.inventory",
  INVENTORY_VIEW: "inventory.view",
  INVENTORY_CATALOGUE: "inventory.catalogue",
  INVENTORY_ADJUST: "inventory.adjust",
  INVENTORY_TRANSFER: "inventory.transfer",
  INVENTORY_ISSUE: "inventory.issue",
  SUPPLIERS_VIEW: "suppliers.view",
  SUPPLIERS_MANAGE: "suppliers.manage",
  PURCHASING_MANAGE: "purchasing.manage",
  PURCHASING_APPROVE: "purchasing.approve",
  PURCHASING_RECEIVE: "purchasing.receive",
} as const;

export type PermissionCode = (typeof P)[keyof typeof P];

/**
 * UI-only permission check, used to hide actions the user cannot perform.
 * The API enforces every permission independently; this is never a security boundary.
 */
export function can(me: Me, permission: PermissionCode, branchId?: string | null): boolean {
  if (me.is_owner || me.permissions.includes(permission)) return true;
  if (!branchId) return false;
  return me.branch_permissions[branchId]?.includes(permission) ?? false;
}

export function canInAnyBranch(me: Me, permission: PermissionCode): boolean {
  return (
    can(me, permission) ||
    Object.values(me.branch_permissions).some((perms) => perms.includes(permission))
  );
}
