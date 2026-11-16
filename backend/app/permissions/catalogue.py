"""Permission catalogue — the single source of truth for permission codes.

Roles store permission codes as text; every code must exist here. Add new permissions
alongside the feature that enforces them, and grant them to default role templates
with a data migration (see DEFAULT_ROLES and docs/architecture/permissions.md).
"""

from dataclasses import dataclass
from enum import StrEnum


class Scope(StrEnum):
    # Granted only through an organisation-wide role assignment.
    ORGANISATION = "organisation"
    # May be granted organisation-wide or for specific branches.
    BRANCH = "branch"


@dataclass(frozen=True)
class PermissionDef:
    code: str
    module: str
    label: str
    description: str
    scope: Scope


class P(StrEnum):
    """Permission codes. Use these constants in code, never string literals."""

    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    BRANCHES_VIEW = "branches.view"
    BRANCHES_MANAGE = "branches.manage"
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    AUDIT_VIEW = "audit.view"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_MANAGE = "customers.manage"
    VEHICLES_VIEW = "vehicles.view"
    VEHICLES_MANAGE = "vehicles.manage"
    JOB_CARDS_VIEW = "job_cards.view"
    JOB_CARDS_CREATE = "job_cards.create"
    JOB_CARDS_MANAGE = "job_cards.manage"
    JOB_CARDS_ASSIGN = "job_cards.assign"
    JOB_CARDS_WORK = "job_cards.work"
    JOB_CARDS_AUTHORISE_EXCEPTION = "job_cards.authorise_exception"
    INSPECTIONS_PERFORM = "inspections.perform"
    INSPECTIONS_AMEND = "inspections.amend"
    INSPECTION_TEMPLATES_MANAGE = "inspection_templates.manage"
    APPOINTMENTS_VIEW = "appointments.view"
    APPOINTMENTS_MANAGE = "appointments.manage"
    QUOTATIONS_VIEW = "quotations.view"
    QUOTATIONS_MANAGE = "quotations.manage"
    QUOTATIONS_RECORD_DECISION = "quotations.record_decision"
    INVOICES_VIEW = "invoices.view"
    INVOICES_MANAGE = "invoices.manage"
    INVOICES_CREDIT = "invoices.credit"
    PAYMENTS_RECORD = "payments.record"
    PAYMENTS_REFUND = "payments.refund"


PERMISSIONS: tuple[PermissionDef, ...] = (
    PermissionDef(
        P.SETTINGS_VIEW,
        "Organisation",
        "View organisation settings",
        "View organisation profile, tax rates and document numbering.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.SETTINGS_MANAGE,
        "Organisation",
        "Manage organisation settings",
        "Edit organisation profile, preferences, tax rates and document numbering.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.BRANCHES_VIEW,
        "Branches",
        "View branches",
        "View branch details, operating hours and service bays.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.BRANCHES_MANAGE,
        "Branches",
        "Manage branches",
        "Edit branch details, hours and service bays. Creating or archiving branches "
        "requires an organisation-wide assignment.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.USERS_VIEW,
        "Users and roles",
        "View users and roles",
        "View staff accounts, their roles and role definitions.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.USERS_MANAGE,
        "Users and roles",
        "Manage users",
        "Invite, edit, deactivate users and assign roles. A user can only assign roles "
        "whose permissions they hold themselves.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.ROLES_MANAGE,
        "Users and roles",
        "Manage roles",
        "Create and edit roles and their permissions.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.AUDIT_VIEW,
        "Audit",
        "View audit log",
        "View the audit trail of security and business events.",
        Scope.ORGANISATION,
    ),
    # Customers and vehicles are shared by every branch of the organisation, so a grant
    # in any branch gives access to all of them (Principal.require_in_any_branch).
    PermissionDef(
        P.CUSTOMERS_VIEW,
        "Customers and vehicles",
        "View customers",
        "View customer profiles, contact details and communication consent.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.CUSTOMERS_MANAGE,
        "Customers and vehicles",
        "Manage customers",
        "Register and edit customers, record communication consent, archive customers.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.VEHICLES_VIEW,
        "Customers and vehicles",
        "View vehicles",
        "View vehicles, ownership history and existing-damage notes.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.VEHICLES_MANAGE,
        "Customers and vehicles",
        "Manage vehicles",
        "Register and edit vehicles, transfer ownership, archive vehicles.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_VIEW,
        "Job cards",
        "View job cards",
        "View every job card in the branch, with history, notes and assignments.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_CREATE,
        "Job cards",
        "Receive vehicles",
        "Book vehicles in and open job cards.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_MANAGE,
        "Job cards",
        "Manage job cards",
        "Edit job details, move jobs through every status, hand over and cancel jobs.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_ASSIGN,
        "Job cards",
        "Assign mechanics",
        "Assign and unassign mechanics on job cards.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_WORK,
        "Job cards",
        "Work on assigned jobs",
        "See jobs assigned to you, add notes and diagnosis, and make workshop status "
        "updates (start diagnosis, send for approval, start repair, send to quality check).",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.JOB_CARDS_AUTHORISE_EXCEPTION,
        "Job cards",
        "Authorise work without quotation approval",
        "Record a documented exception so chargeable work may start before a quotation is "
        "approved. Every exception records who, when, why and the scope.",
        Scope.BRANCH,
    ),
    # Viewing an inspection follows job card visibility (anyone who can see the job).
    PermissionDef(
        P.INSPECTIONS_PERFORM,
        "Inspections",
        "Carry out inspections",
        "Start inspections on visible job cards, record results, notes and photos, and submit.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.INSPECTIONS_AMEND,
        "Inspections",
        "Amend submitted inspections",
        "Correct a submitted inspection. Every amendment records the old value and a reason.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.INSPECTION_TEMPLATES_MANAGE,
        "Inspections",
        "Manage inspection templates",
        "Create and edit the checklists used for inspections.",
        Scope.ORGANISATION,
    ),
    PermissionDef(
        P.APPOINTMENTS_VIEW,
        "Appointments",
        "View appointments",
        "View the branch booking calendar.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.APPOINTMENTS_MANAGE,
        "Appointments",
        "Manage appointments",
        "Book, reschedule, cancel and check in appointments.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.QUOTATIONS_VIEW,
        "Quotations",
        "View quotations",
        "View quotations, versions, totals and customer decisions.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.QUOTATIONS_MANAGE,
        "Quotations",
        "Prepare and send quotations",
        "Create quotations, edit drafts, send them to customers and create revisions.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.QUOTATIONS_RECORD_DECISION,
        "Quotations",
        "Record customer approval",
        "Record a customer's approval or rejection given in person, by phone or message, "
        "with evidence.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.INVOICES_VIEW,
        "Invoices and payments",
        "View invoices and payments",
        "View invoices, credit notes, payments, receipts and customer balances.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.INVOICES_MANAGE,
        "Invoices and payments",
        "Prepare and issue invoices",
        "Create and edit draft invoices and issue them. Issued invoices cannot be changed.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.INVOICES_CREDIT,
        "Invoices and payments",
        "Issue credit notes",
        "Reduce the amount owed on an issued invoice with a credit note and a reason.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.PAYMENTS_RECORD,
        "Invoices and payments",
        "Record payments",
        "Record money received and allocate it to invoices; issue receipts.",
        Scope.BRANCH,
    ),
    PermissionDef(
        P.PAYMENTS_REFUND,
        "Invoices and payments",
        "Refund and reverse payments",
        "Reverse a mistakenly recorded payment or refund an overpayment, with a reason.",
        Scope.BRANCH,
    ),
)

PERMISSIONS_BY_CODE: dict[str, PermissionDef] = {p.code: p for p in PERMISSIONS}
ALL_PERMISSION_CODES: frozenset[str] = frozenset(PERMISSIONS_BY_CODE)


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    name: str
    description: str
    permissions: frozenset[str]
    is_owner: bool = False


DEFAULT_ROLES: tuple[RoleTemplate, ...] = (
    RoleTemplate(
        "owner",
        "Owner",
        "Full access to everything, including all future permissions. Cannot be edited.",
        ALL_PERMISSION_CODES,
        is_owner=True,
    ),
    RoleTemplate(
        "administrator",
        "Administrator",
        "Manages organisation settings, branches, users and roles.",
        ALL_PERMISSION_CODES,
    ),
    RoleTemplate(
        "workshop_manager",
        "Workshop manager",
        "Runs day-to-day workshop operations for a branch.",
        frozenset(
            {
                P.BRANCHES_VIEW,
                P.USERS_VIEW,
                P.CUSTOMERS_VIEW,
                P.CUSTOMERS_MANAGE,
                P.VEHICLES_VIEW,
                P.VEHICLES_MANAGE,
                P.JOB_CARDS_VIEW,
                P.JOB_CARDS_CREATE,
                P.JOB_CARDS_MANAGE,
                P.JOB_CARDS_ASSIGN,
                P.JOB_CARDS_WORK,
                P.JOB_CARDS_AUTHORISE_EXCEPTION,
                P.INSPECTIONS_PERFORM,
                P.INSPECTIONS_AMEND,
                P.APPOINTMENTS_VIEW,
                P.APPOINTMENTS_MANAGE,
                P.QUOTATIONS_VIEW,
                P.QUOTATIONS_MANAGE,
                P.QUOTATIONS_RECORD_DECISION,
                P.INVOICES_VIEW,
                P.INVOICES_MANAGE,
                P.INVOICES_CREDIT,
                P.PAYMENTS_RECORD,
                P.PAYMENTS_REFUND,
            }
        ),
    ),
    RoleTemplate(
        "service_advisor",
        "Service advisor",
        "Handles customers, bookings, quotations and vehicle handover.",
        frozenset(
            {
                P.BRANCHES_VIEW,
                P.CUSTOMERS_VIEW,
                P.CUSTOMERS_MANAGE,
                P.VEHICLES_VIEW,
                P.VEHICLES_MANAGE,
                P.JOB_CARDS_VIEW,
                P.JOB_CARDS_CREATE,
                P.JOB_CARDS_MANAGE,
                P.INSPECTIONS_PERFORM,
                P.APPOINTMENTS_VIEW,
                P.APPOINTMENTS_MANAGE,
                P.QUOTATIONS_VIEW,
                P.QUOTATIONS_MANAGE,
                P.QUOTATIONS_RECORD_DECISION,
                P.INVOICES_VIEW,
                P.INVOICES_MANAGE,
                P.PAYMENTS_RECORD,
            }
        ),
    ),
    RoleTemplate(
        "mechanic",
        "Mechanic",
        "Works on assigned jobs, inspections and repairs.",
        frozenset(
            {
                P.BRANCHES_VIEW,
                P.CUSTOMERS_VIEW,
                P.VEHICLES_VIEW,
                P.JOB_CARDS_WORK,
                P.INSPECTIONS_PERFORM,
                P.APPOINTMENTS_VIEW,
            }
        ),
    ),
    RoleTemplate(
        "inventory_manager",
        "Inventory manager",
        "Manages parts, stock, suppliers and purchasing.",
        frozenset({P.BRANCHES_VIEW}),
    ),
    RoleTemplate(
        "accounts",
        "Accounts / cashier",
        "Handles invoices, payments and receipts.",
        frozenset(
            {
                P.BRANCHES_VIEW,
                P.CUSTOMERS_VIEW,
                P.VEHICLES_VIEW,
                P.JOB_CARDS_VIEW,
                P.QUOTATIONS_VIEW,
                P.INVOICES_VIEW,
                P.INVOICES_MANAGE,
                P.INVOICES_CREDIT,
                P.PAYMENTS_RECORD,
                P.PAYMENTS_REFUND,
            }
        ),
    ),
)
