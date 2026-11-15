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
        frozenset({P.BRANCHES_VIEW, P.USERS_VIEW}),
    ),
    RoleTemplate(
        "service_advisor",
        "Service advisor",
        "Handles customers, bookings, quotations and vehicle handover.",
        frozenset({P.BRANCHES_VIEW}),
    ),
    RoleTemplate(
        "mechanic",
        "Mechanic",
        "Works on assigned jobs, inspections and repairs.",
        frozenset({P.BRANCHES_VIEW}),
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
        frozenset({P.BRANCHES_VIEW}),
    ),
)
