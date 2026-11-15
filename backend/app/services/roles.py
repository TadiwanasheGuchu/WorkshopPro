"""Roles and their permissions.

Escalation rule: a user can only add permissions to a role if they hold those
permissions organisation-wide themselves. The owner role cannot be edited.
"""

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, PermissionDeniedError
from app.core.time import utcnow
from app.models import Role, RolePermission, UserRoleAssignment
from app.permissions.catalogue import ALL_PERMISSION_CODES, P
from app.permissions.principal import Principal
from app.schemas.user import RoleCreate, RoleRead, RoleUpdate
from app.services import audit
from app.services.common import get_scoped


class UnknownPermissionError(AppError):
    status_code = 422
    code = "unknown_permission"


def role_permissions(db: Session, role_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    result: dict[uuid.UUID, set[str]] = defaultdict(set)
    if role_ids:
        for role_id, perm in db.execute(
            select(RolePermission.role_id, RolePermission.permission).where(
                RolePermission.role_id.in_(role_ids)
            )
        ):
            result[role_id].add(perm)
    return result


def effective_permissions(role: Role, perms: set[str]) -> set[str]:
    return set(ALL_PERMISSION_CODES) if role.is_owner else perms & ALL_PERMISSION_CODES


def _validate_permissions(permissions: list[str]) -> set[str]:
    unknown = sorted(set(permissions) - ALL_PERMISSION_CODES)
    if unknown:
        raise UnknownPermissionError("Unknown permission codes.", details={"unknown": unknown})
    return set(permissions)


def _require_can_grant(principal: Principal, permissions: set[str]) -> None:
    missing = sorted(permissions - principal.effective_org_permissions())
    if missing:
        raise PermissionDeniedError(
            "You cannot grant permissions you do not hold yourself.",
            details={"missing": missing},
        )


def _to_read(db: Session, roles: list[Role]) -> list[RoleRead]:
    ids = [r.id for r in roles]
    perms = role_permissions(db, ids)
    counts = (
        dict(
            db.execute(
                select(
                    UserRoleAssignment.role_id,
                    func.count(func.distinct(UserRoleAssignment.user_id)),
                )
                .where(UserRoleAssignment.role_id.in_(ids))
                .group_by(UserRoleAssignment.role_id)
            ).all()
        )
        if ids
        else {}
    )
    return [
        RoleRead(
            id=r.id,
            name=r.name,
            description=r.description,
            is_owner=r.is_owner,
            template_key=r.template_key,
            archived_at=r.archived_at,
            permissions=sorted(effective_permissions(r, perms.get(r.id, set()))),
            user_count=counts.get(r.id, 0),
        )
        for r in roles
    ]


def list_roles(
    db: Session, principal: Principal, *, include_archived: bool = False
) -> list[RoleRead]:
    principal.require(P.USERS_VIEW)
    stmt = select(Role).where(Role.organisation_id == principal.organisation_id)
    if not include_archived:
        stmt = stmt.where(Role.archived_at.is_(None))
    roles = list(db.scalars(stmt.order_by(Role.is_owner.desc(), Role.name)))
    return _to_read(db, roles)


def get_role(db: Session, principal: Principal, role_id: uuid.UUID) -> RoleRead:
    principal.require(P.USERS_VIEW)
    role = get_scoped(db, Role, role_id, principal.organisation_id)
    return _to_read(db, [role])[0]


def create_role(db: Session, principal: Principal, body: RoleCreate) -> RoleRead:
    principal.require(P.ROLES_MANAGE)
    perms = _validate_permissions(body.permissions)
    _require_can_grant(principal, perms)
    role = Role(
        organisation_id=principal.organisation_id, name=body.name, description=body.description
    )
    db.add(role)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A role with this name already exists.") from exc
    db.add_all(RolePermission(role_id=role.id, permission=p) for p in perms)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="role.created",
        entity_type="role",
        entity_id=role.id,
        summary=f"Role {role.name} created",
        changes={"permissions": sorted(perms)},
    )
    db.commit()
    return _to_read(db, [role])[0]


def update_role(
    db: Session, principal: Principal, role_id: uuid.UUID, body: RoleUpdate
) -> RoleRead:
    principal.require(P.ROLES_MANAGE)
    role = get_scoped(db, Role, role_id, principal.organisation_id)
    if role.is_owner:
        raise ConflictError("The owner role cannot be changed.")
    data = body.changes()
    changes: dict[str, list[object]] = {}

    if "permissions" in data:
        new_perms = _validate_permissions(data.pop("permissions"))
        old_perms = role_permissions(db, [role.id]).get(role.id, set())
        added, removed = new_perms - old_perms, old_perms - new_perms
        _require_can_grant(principal, added)
        if added or removed:
            db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            db.add_all(RolePermission(role_id=role.id, permission=p) for p in new_perms)
            changes["permissions_added"] = sorted(added)  # type: ignore[assignment]
            changes["permissions_removed"] = sorted(removed)  # type: ignore[assignment]

    for key, value in data.items():
        old = getattr(role, key)
        if old != value:
            changes[key] = [old, value]
            setattr(role, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A role with this name already exists.") from exc
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="role.updated",
            entity_type="role",
            entity_id=role.id,
            summary=f"Role {role.name} updated",
            changes=changes,
        )
    db.commit()
    return _to_read(db, [role])[0]


def set_archived(db: Session, principal: Principal, role_id: uuid.UUID, archived: bool) -> RoleRead:
    principal.require(P.ROLES_MANAGE)
    role = get_scoped(db, Role, role_id, principal.organisation_id)
    if role.is_owner:
        raise ConflictError("The owner role cannot be archived.")
    if archived == (role.archived_at is not None):
        return _to_read(db, [role])[0]
    if archived:
        in_use = db.scalar(
            select(func.count())
            .select_from(UserRoleAssignment)
            .where(UserRoleAssignment.role_id == role.id)
        )
        if in_use:
            raise ConflictError(
                "Remove this role from all users before archiving it.",
                details={"assignments": in_use},
            )
    role.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="role.archived" if archived else "role.restored",
        entity_type="role",
        entity_id=role.id,
        summary=f"Role {role.name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return _to_read(db, [role])[0]
