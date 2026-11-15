"""Staff accounts: invitations, profile edits, activation and role assignments.

Escalation rules:
- A user can only assign or remove roles whose permissions they hold organisation-wide.
- Only owners can grant or remove the owner role, or change an owner's account.
- An organisation always keeps at least one active owner.
- Users cannot deactivate themselves.
"""

import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, PermissionDeniedError
from app.core.time import utcnow
from app.integrations.email import OutgoingEmail
from app.models import Branch, Organisation, Role, User, UserRoleAssignment, UserToken
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.common import PageParams
from app.schemas.user import (
    RoleAssignmentInput,
    RoleAssignmentRead,
    UserInvite,
    UserRead,
    UserStatus,
    UserUpdate,
)
from app.services import audit, auth, emails
from app.services.common import get_scoped, paginate
from app.services.roles import effective_permissions, role_permissions


class InvalidAssignmentError(AppError):
    status_code = 422
    code = "invalid_role_assignment"


def status_of(user: User) -> UserStatus:
    if not user.is_active:
        return "deactivated"
    return "active" if user.password_hash else "invited"


# --------------------------------------------------------------------------- reads


def _assignments_for(
    db: Session, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[RoleAssignmentRead]]:
    result: dict[uuid.UUID, list[RoleAssignmentRead]] = defaultdict(list)
    if not user_ids:
        return result
    rows = db.execute(
        select(UserRoleAssignment, Role.name, Branch.name)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .outerjoin(Branch, Branch.id == UserRoleAssignment.branch_id)
        .where(UserRoleAssignment.user_id.in_(user_ids))
        .order_by(Role.name, Branch.name.nulls_first())
    )
    for assignment, role_name, branch_name in rows:
        result[assignment.user_id].append(
            RoleAssignmentRead(
                id=assignment.id,
                role_id=assignment.role_id,
                role_name=role_name,
                branch_id=assignment.branch_id,
                branch_name=branch_name,
            )
        )
    return result


def _owner_ids(db: Session, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not user_ids:
        return set()
    return set(
        db.scalars(
            select(UserRoleAssignment.user_id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(UserRoleAssignment.user_id.in_(user_ids), Role.is_owner)
        )
    )


def to_read(db: Session, users: list[User]) -> list[UserRead]:
    ids = [u.id for u in users]
    assignments = _assignments_for(db, ids)
    owners = _owner_ids(db, ids)
    return [
        UserRead(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            phone=u.phone,
            status=status_of(u),
            is_owner=u.id in owners,
            last_login_at=u.last_login_at,
            invited_at=u.invited_at,
            activated_at=u.activated_at,
            created_at=u.created_at,
            role_assignments=assignments.get(u.id, []),
        )
        for u in users
    ]


def list_users(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    status: UserStatus | None = None,
    role_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> tuple[list[UserRead], int]:
    principal.require(P.USERS_VIEW)
    stmt = select(User).where(User.organisation_id == principal.organisation_id)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if status == "deactivated":
        stmt = stmt.where(User.is_active.is_(False))
    elif status == "invited":
        stmt = stmt.where(User.is_active, User.password_hash.is_(None))
    elif status == "active":
        stmt = stmt.where(User.is_active, User.password_hash.is_not(None))
    if role_id or branch_id:
        sub = select(UserRoleAssignment.id).where(UserRoleAssignment.user_id == User.id)
        if role_id:
            sub = sub.where(UserRoleAssignment.role_id == role_id)
        if branch_id:
            # Users working in a branch: assigned to it, or organisation-wide.
            sub = sub.where(
                or_(
                    UserRoleAssignment.branch_id == branch_id,
                    UserRoleAssignment.branch_id.is_(None),
                )
            )
        stmt = stmt.where(exists(sub))
    users, total = paginate(db, stmt.order_by(User.is_active.desc(), User.full_name), params)
    return to_read(db, users), total


def get_user(db: Session, principal: Principal, user_id: uuid.UUID) -> UserRead:
    principal.require(P.USERS_VIEW)
    user = get_scoped(db, User, user_id, principal.organisation_id)
    return to_read(db, [user])[0]


# --------------------------------------------------------------------------- guards


def _is_owner(db: Session, user_id: uuid.UUID) -> bool:
    return bool(_owner_ids(db, [user_id]))


def _require_can_manage_user(db: Session, principal: Principal, target: User) -> None:
    principal.require(P.USERS_MANAGE)
    if _is_owner(db, target.id) and not principal.is_owner:
        raise PermissionDeniedError("Only an owner can change an owner's account.")


def _active_owner_count(db: Session, organisation_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(User.id)))
            .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(
                User.organisation_id == organisation_id,
                User.is_active,
                User.password_hash.is_not(None),
                Role.is_owner,
            )
        )
        or 0
    )


def _resolve_assignments(
    db: Session, principal: Principal, inputs: list[RoleAssignmentInput]
) -> dict[tuple[uuid.UUID, uuid.UUID | None], Role]:
    """Validate requested assignments belong to this organisation and are usable."""
    role_ids = {a.role_id for a in inputs}
    branch_ids = {a.branch_id for a in inputs if a.branch_id}
    roles = {
        r.id: r
        for r in db.scalars(
            select(Role).where(
                Role.id.in_(role_ids), Role.organisation_id == principal.organisation_id
            )
        )
    }
    branches = {
        b.id: b
        for b in db.scalars(
            select(Branch).where(
                Branch.id.in_(branch_ids), Branch.organisation_id == principal.organisation_id
            )
        )
    }
    resolved: dict[tuple[uuid.UUID, uuid.UUID | None], Role] = {}
    for a in inputs:
        role = roles.get(a.role_id)
        if role is None:
            raise InvalidAssignmentError("Role not found.", details={"role_id": str(a.role_id)})
        if role.archived_at is not None:
            raise InvalidAssignmentError(f"Role {role.name} is archived.")
        if a.branch_id is not None:
            branch = branches.get(a.branch_id)
            if branch is None:
                raise InvalidAssignmentError(
                    "Branch not found.", details={"branch_id": str(a.branch_id)}
                )
            if branch.archived_at is not None:
                raise InvalidAssignmentError(f"Branch {branch.name} is archived.")
            if role.is_owner:
                raise InvalidAssignmentError("The owner role applies to all branches.")
        resolved[(a.role_id, a.branch_id)] = role
    return resolved


def _require_can_assign(db: Session, principal: Principal, roles: list[Role]) -> None:
    """The actor must hold every permission of each role they add or remove."""
    if not roles:
        return
    if any(r.is_owner for r in roles) and not principal.is_owner:
        raise PermissionDeniedError("Only an owner can grant or remove the owner role.")
    perms = role_permissions(db, [r.id for r in roles])
    held = principal.effective_org_permissions()
    missing: set[str] = set()
    for role in roles:
        missing |= effective_permissions(role, perms.get(role.id, set())) - held
    if missing:
        raise PermissionDeniedError(
            "You cannot assign or remove a role with permissions you do not hold.",
            details={"missing": sorted(missing)},
        )


# --------------------------------------------------------------------------- writes


def invite_user(
    db: Session, principal: Principal, settings: Settings, body: UserInvite
) -> tuple[UserRead, OutgoingEmail]:
    principal.require(P.USERS_MANAGE)
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise ConflictError("A user with this email already exists.")
    resolved = _resolve_assignments(db, principal, body.role_assignments)
    _require_can_assign(db, principal, list(resolved.values()))

    user = User(
        organisation_id=principal.organisation_id,
        email=body.email,
        full_name=body.full_name,
        phone=body.phone,
        invited_at=utcnow(),
    )
    db.add(user)
    db.flush()
    for role_id, branch_id in resolved:
        db.add(
            UserRoleAssignment(
                organisation_id=principal.organisation_id,
                user_id=user.id,
                role_id=role_id,
                branch_id=branch_id,
                created_by_user_id=principal.user_id,
            )
        )
    token = auth.issue_user_token(
        db,
        user,
        "invitation",
        timedelta(days=settings.invitation_token_days),
        created_by=principal.user_id,
    )
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="user.invited",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} ({user.email}) invited",
        changes={
            "role_assignments": [{"role": r.name, "branch_id": b} for (_, b), r in resolved.items()]
        },
    )
    db.commit()
    org = db.get_one(Organisation, principal.organisation_id)
    email = emails.invitation_email(
        to=user.email, full_name=user.full_name, organisation_name=org.name, token=token
    )
    return to_read(db, [user])[0], email


def resend_invitation(
    db: Session, principal: Principal, settings: Settings, user_id: uuid.UUID
) -> OutgoingEmail:
    user = get_scoped(db, User, user_id, principal.organisation_id)
    _require_can_manage_user(db, principal, user)
    if status_of(user) != "invited":
        raise ConflictError(
            "Only users who have not yet accepted their invitation can be re-invited."
        )
    token = auth.issue_user_token(
        db,
        user,
        "invitation",
        timedelta(days=settings.invitation_token_days),
        created_by=principal.user_id,
    )
    user.invited_at = utcnow()
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="user.invitation_resent",
        entity_type="user",
        entity_id=user.id,
        summary=f"Invitation resent to {user.email}",
    )
    db.commit()
    org = db.get_one(Organisation, principal.organisation_id)
    return emails.invitation_email(
        to=user.email, full_name=user.full_name, organisation_name=org.name, token=token
    )


def update_user(
    db: Session, principal: Principal, user_id: uuid.UUID, body: UserUpdate
) -> UserRead:
    user = get_scoped(db, User, user_id, principal.organisation_id)
    _require_can_manage_user(db, principal, user)
    data = body.changes()
    if "email" in data and data["email"].lower() != user.email.lower():
        taken = db.scalar(select(User.id).where(User.email == data["email"], User.id != user.id))
        if taken:
            raise ConflictError("A user with this email already exists.")
    changes: dict[str, list[object]] = {}
    for key, value in data.items():
        old = getattr(user, key)
        if old != value:
            changes[key] = [old, value]
            setattr(user, key, value)
    if "email" in changes:
        # Outstanding links were sent to the old address.
        db.execute(
            update(UserToken)
            .where(UserToken.user_id == user.id, UserToken.used_at.is_(None))
            .values(revoked_at=utcnow())
        )
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            actor=principal,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            summary=f"User {user.full_name} updated",
            changes=changes,
        )
    db.commit()
    return to_read(db, [user])[0]


def set_active(db: Session, principal: Principal, user_id: uuid.UUID, active: bool) -> UserRead:
    user = get_scoped(db, User, user_id, principal.organisation_id)
    _require_can_manage_user(db, principal, user)
    if user.is_active == active:
        return to_read(db, [user])[0]
    if not active:
        if user.id == principal.user_id:
            raise ConflictError("You cannot deactivate your own account.")
        user.is_active = False
        user.deactivated_at = utcnow()
        db.flush()
        if _active_owner_count(db, principal.organisation_id) == 0:
            db.rollback()
            raise ConflictError("The organisation must keep at least one active owner.")
        auth.revoke_user_sessions(db, user.id)
        db.execute(
            update(UserToken)
            .where(UserToken.user_id == user.id, UserToken.used_at.is_(None))
            .values(revoked_at=utcnow())
        )
    else:
        user.is_active = True
        user.deactivated_at = None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="user.activated" if active else "user.deactivated",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} {'reactivated' if active else 'deactivated'}",
    )
    db.commit()
    return to_read(db, [user])[0]


def set_role_assignments(
    db: Session, principal: Principal, user_id: uuid.UUID, inputs: list[RoleAssignmentInput]
) -> UserRead:
    user = get_scoped(db, User, user_id, principal.organisation_id)
    _require_can_manage_user(db, principal, user)
    desired = _resolve_assignments(db, principal, inputs)

    current = {
        (a.role_id, a.branch_id): a
        for a in db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id))
    }
    to_add = [k for k in desired if k not in current]
    to_remove = [k for k in current if k not in desired]
    if not to_add and not to_remove:
        return to_read(db, [user])[0]

    removed_roles = list(
        db.scalars(select(Role).where(Role.id.in_({role_id for role_id, _ in to_remove})))
    )
    _require_can_assign(db, principal, [desired[k] for k in to_add] + removed_roles)
    role_names = {r.id: r.name for r in removed_roles} | {r.id: r.name for r in desired.values()}

    for key in to_remove:
        db.delete(current[key])
    for role_id, branch_id in to_add:
        db.add(
            UserRoleAssignment(
                organisation_id=principal.organisation_id,
                user_id=user.id,
                role_id=role_id,
                branch_id=branch_id,
                created_by_user_id=principal.user_id,
            )
        )
    db.flush()
    if _active_owner_count(db, principal.organisation_id) == 0:
        db.rollback()
        raise ConflictError("The organisation must keep at least one active owner.")

    audit.record(
        db,
        organisation_id=principal.organisation_id,
        actor=principal,
        action="user.roles_changed",
        entity_type="user",
        entity_id=user.id,
        summary=f"Roles changed for {user.full_name}",
        changes={
            "added": [{"role": role_names[r], "branch_id": b} for r, b in to_add],
            "removed": [{"role": role_names[r], "branch_id": b} for r, b in to_remove],
        },
    )
    db.commit()
    return to_read(db, [user])[0]
