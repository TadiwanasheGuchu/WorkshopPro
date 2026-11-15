"""The authenticated caller and their effective permissions.

Loaded once per request from the user's role assignments. Permission changes therefore
take effect on the user's next request without signing out.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError
from app.models import Branch, Role, RolePermission, User, UserRoleAssignment
from app.permissions.catalogue import ALL_PERMISSION_CODES, PERMISSIONS_BY_CODE, Scope


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    full_name: str
    session_id: uuid.UUID | None
    is_owner: bool = False
    # Permissions granted through organisation-wide assignments.
    org_permissions: frozenset[str] = frozenset()
    # Permissions granted through branch-scoped assignments, per branch.
    branch_permissions: dict[uuid.UUID, frozenset[str]] = field(default_factory=dict)
    # True if the user has at least one organisation-wide role (works in all branches).
    has_org_wide_role: bool = False
    # Branches the user is assigned to through branch-scoped roles.
    assigned_branch_ids: frozenset[uuid.UUID] = frozenset()

    def can(self, permission: str, branch_id: uuid.UUID | None = None) -> bool:
        """True if the caller holds `permission` organisation-wide, or for `branch_id`.

        Organisation-scoped permissions are only ever satisfied by an organisation-wide
        grant, even if a branch is given.
        """
        if self.is_owner or permission in self.org_permissions:
            return True
        if branch_id is None:
            return False
        definition = PERMISSIONS_BY_CODE.get(permission)
        if definition is None or definition.scope is Scope.ORGANISATION:
            return False
        return permission in self.branch_permissions.get(branch_id, frozenset())

    def require(self, permission: str, branch_id: uuid.UUID | None = None) -> None:
        if not self.can(permission, branch_id):
            raise PermissionDeniedError("You do not have permission to perform this action.")

    def can_in_any_branch(self, permission: str) -> bool:
        return self.can(permission) or any(
            permission in perms for perms in self.branch_permissions.values()
        )

    def require_in_any_branch(self, permission: str) -> None:
        """For organisation-wide data (customers, vehicles) that every branch works with."""
        if not self.can_in_any_branch(permission):
            raise PermissionDeniedError("You do not have permission to perform this action.")

    def branch_ids_with(self, permission: str) -> set[uuid.UUID] | None:
        """Branches where `permission` applies. None means all branches."""
        if self.can(permission):
            return None
        return {b for b, perms in self.branch_permissions.items() if permission in perms}

    def effective_org_permissions(self) -> frozenset[str]:
        return ALL_PERMISSION_CODES if self.is_owner else self.org_permissions


def load_principal(db: Session, user: User, session_id: uuid.UUID | None) -> Principal:
    rows = db.execute(
        select(UserRoleAssignment.branch_id, Role.is_owner, RolePermission.permission)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.id)
        .outerjoin(Branch, Branch.id == UserRoleAssignment.branch_id)
        .where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.organisation_id == user.organisation_id,
            Role.archived_at.is_(None),
            # Assignments to archived branches grant nothing.
            Branch.archived_at.is_(None),
        )
    ).all()

    is_owner = False
    org_perms: set[str] = set()
    branch_perms: dict[uuid.UUID, set[str]] = defaultdict(set)
    org_wide = False
    assigned: set[uuid.UUID] = set()
    for branch_id, role_is_owner, permission in rows:
        if branch_id is None:
            org_wide = True
            is_owner = is_owner or role_is_owner
        else:
            assigned.add(branch_id)
        if permission is None or permission not in ALL_PERMISSION_CODES:
            continue
        if branch_id is None:
            org_perms.add(permission)
        else:
            branch_perms[branch_id].add(permission)

    return Principal(
        user_id=user.id,
        organisation_id=user.organisation_id,
        email=user.email,
        full_name=user.full_name,
        session_id=session_id,
        is_owner=is_owner,
        org_permissions=frozenset(org_perms),
        branch_permissions={b: frozenset(p) for b, p in branch_perms.items()},
        has_org_wide_role=org_wide,
        assigned_branch_ids=frozenset(assigned),
    )
