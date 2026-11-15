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
