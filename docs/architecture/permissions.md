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

## Current catalogue

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
| `customers.view` | branch* | View customers, contacts, consent |
| `customers.manage` | branch* | Register/edit/archive customers, record consent |
| `vehicles.view` | branch* | View vehicles and ownership history |
| `vehicles.manage` | branch* | Register/edit/transfer/archive vehicles |

| `job_cards.view` | branch | View every job card in the branch |
| `job_cards.create` | branch | Receive vehicles (open job cards) |
| `job_cards.manage` | branch | Edit job details, every status change, hand over, cancel |
| `job_cards.assign` | branch | Assign/unassign mechanics |
| `job_cards.work` | branch | See jobs assigned to you; diagnosis/work notes; workshop status moves |
| `job_cards.authorise_exception` | branch | Authorise chargeable work without an approved quotation |

| `inspections.perform` | branch | Start inspections, record results/photos, submit (on jobs you can see) |
| `inspections.amend` | branch | Correct submitted inspections (old value + reason recorded) |
| `inspection_templates.manage` | organisation | Create and edit inspection checklists |
| `appointments.view` | branch | View the branch booking calendar |
| `appointments.manage` | branch | Book, reschedule, cancel, mark no-show, check in |

| `quotations.view` | branch | View quotations, versions and decisions |
| `quotations.manage` | branch | Prepare, send, revise quotations; read tax rates |
| `quotations.record_decision` | branch | Record a customer's approval/rejection given offline, with evidence |
| `invoices.view` | branch | View invoices, credit notes, payments and customer balances |
| `invoices.manage` | branch | Start, edit, delete and issue draft invoices |
| `invoices.credit` | branch | Issue credit notes against issued invoices |
| `payments.record` | branch | Record payments received and apply customer credit |
| `payments.refund` | branch | Refund overpayments and reverse payments recorded in error |
| `reports.operational` | branch | Operations report: jobs, turnaround, quotation outcomes, mechanic workload |
| `reports.financial` | branch | Financial report: invoiced, credited, received, refunds, receivables |
| `notifications.view` | branch | Customer notification log and templates (read); retry failed messages |
| `notifications.manage` | organisation | Turn notifications on or off; edit templates and WhatsApp template names |
| `reports.inventory` | branch | Inventory report: stock value at cost, movements, parts used, purchasing, stock check |
| `inventory.view` | branch | Parts catalogue, stock levels and movements for the branch (costs hidden) |
| `inventory.catalogue` | organisation | Add and edit parts, categories and prices; see cost prices |
| `inventory.adjust` | branch | Opening stock, stocktake adjustments, minimum levels, stock locations; see cost prices |
| `inventory.transfer` | branch | Transfer stock; needed in both the sending and receiving branch |
| `inventory.issue` | branch | Reserve, issue and return parts for authorised jobs; release reservations |
| `suppliers.view` | branch | Suppliers, their part codes and prices; the branch's purchase orders |
| `suppliers.manage` | organisation | Add and edit suppliers and their part codes |
| `purchasing.manage` | branch | Prepare and edit draft purchase orders; cancel; close short |
| `purchasing.approve` | branch | Approve draft purchase orders |
| `purchasing.receive` | branch | Receive deliveries into stock; return goods to suppliers |

Viewing an inspection or its photos follows job card visibility: anyone who can see the job can see them.

\* Customers and vehicles are shared by the whole organisation. A grant in **any** branch gives access to all of them (`Principal.require_in_any_branch`), so a branch-limited service advisor can serve a customer who first visited another branch.

## Job card workflow

The transition table lives in `backend/app/services/job_workflow.py`. Assigned mechanics (`job_cards.work`) may start diagnosis, send for approval, start repair, wait for parts and send to quality check. Quality sign-off, handover, cancellation and re-opening need `job_cards.manage`. Entering *awaiting parts* or *repair in progress* from an unapproved state needs an approved quotation (Phase 3) or an active approval exception (409 `approval_required`).

## Default roles (seeded per organisation)

| Role | Permissions now | Gains in later phases |
|---|---|---|
| Owner | everything, always | everything automatically |
| Administrator | all Phase 1 permissions | via data migration |
| Workshop manager | `branches.view`, `users.view`, customers and vehicles (view + manage) | job cards, inspections, scheduling, reports |
| Service advisor | `branches.view`, customers and vehicles (view + manage) | bookings, quotations, invoices (view, manage), payments (record) |
| Mechanic | `branches.view`, `customers.view`, `vehicles.view` | assigned jobs, inspections |
| Inventory manager | `branches.view`, `job_cards.view`, all `inventory.*`, `suppliers.view`, `suppliers.manage`, `purchasing.manage`, `purchasing.receive` | — (approval sits with workshop managers and administrators) |
| Accounts / cashier | `branches.view`, `customers.view`, `vehicles.view` | invoices, credit notes, payments, refunds, financial report |

## Adding a permission

1. Add a `P.*` constant and a `PermissionDef` to the catalogue.
2. Enforce it in the service (`principal.require(...)`), not in the route.
3. Add tests: allowed, denied, cross-organisation.
4. Write a data migration that grants it to the relevant default roles (`roles.template_key`).
5. Mirror the code in `frontend/lib/permissions.ts` and update navigation if needed.

## Customer portal

Portal customers are not staff users and have no permissions from this catalogue. A portal session (`wp_portal_session` cookie, created by a single-use emailed link) authorises only `/api/v1/portal/*`, and every portal query is filtered by the signed-in account's organisation and customer. Another customer's record is reported as not found. Staff sessions are rejected by portal endpoints and portal sessions by staff endpoints. Giving or removing portal access needs `customers.manage`.
