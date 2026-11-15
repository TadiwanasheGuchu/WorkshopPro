# Permissions

Source of truth: `backend/app/permissions/catalogue.py`. The frontend mirror (`frontend/lib/permissions.ts`) only hides UI; the API enforces every check.

## How a check works

```text
request → wp_session cookie → session row (not revoked, not expired, user active)
        → CSRF header matches session (unsafe methods)
        → Principal: org-wide permissions + per-branch permissions (loaded per request)
        → service calls principal.require("users.manage")            # organisation scope
                    or principal.require("branches.manage", branch_id) # branch scope
```

- Records from another organisation return **404**, never 403, so the API never confirms they exist.
- Missing permissions return **403** `permission_denied`.
- A permission with `organisation` scope is never satisfied by a branch-limited role.
- Roles assigned for an archived branch, and archived roles, grant nothing.

## Current catalogue (Phase 1)

| Code | Scope | Grants |
|---|---|---|
| `settings.view` | organisation | View organisation profile, tax rates, numbering, system status |
| `settings.manage` | organisation | Edit the above |
| `branches.view` | branch | View branch details, hours, service bays |
| `branches.manage` | branch | Edit branch, hours, bays (create/archive needs org-wide) |
| `users.view` | organisation | View users and roles |
| `users.manage` | organisation | Invite, edit, deactivate users; assign roles |
| `roles.manage` | organisation | Create and edit roles |
| `audit.view` | organisation | Read the audit log |

## Default roles (seeded per organisation)

| Role | Permissions now | Gains in later phases |
|---|---|---|
| Owner | everything, always | everything automatically |
| Administrator | all Phase 1 permissions | via data migration |
| Workshop manager | `branches.view`, `users.view` | job cards, inspections, scheduling, reports |
| Service advisor | `branches.view` | customers, vehicles, bookings, quotations |
| Mechanic | `branches.view` | assigned jobs, inspections |
| Inventory manager | `branches.view` | parts, stock, suppliers, purchasing |
| Accounts / cashier | `branches.view` | invoices, payments |

## Adding a permission

1. Add a `P.*` constant and a `PermissionDef` to the catalogue.
2. Enforce it in the service (`principal.require(...)`), not in the route.
3. Add tests: allowed, denied, cross-organisation.
4. Write a data migration that grants it to the relevant default roles (`roles.template_key`).
5. Mirror the code in `frontend/lib/permissions.ts` and update navigation if needed.
