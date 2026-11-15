"""Branches, operating hours and service bays."""

import uuid
from datetime import time

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, PermissionDeniedError
from app.core.time import utcnow
from app.models import Branch, BranchOperatingHours, ServiceBay
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.branch import (
    BranchCreate,
    BranchUpdate,
    OperatingHoursUpdate,
    ServiceBayCreate,
    ServiceBayUpdate,
)
from app.schemas.common import PageParams
from app.services import audit
from app.services.common import apply_changes, get_scoped, paginate

# Sensible starting hours; each branch edits its own.
_DEFAULT_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(8), time(17)),
    1: (time(8), time(17)),
    2: (time(8), time(17)),
    3: (time(8), time(17)),
    4: (time(8), time(17)),
    5: (time(8), time(13)),
    6: None,
}


def create_branch_record(
    db: Session, organisation_id: uuid.UUID, *, name: str, code: str, **fields: object
) -> Branch:
    branch = Branch(organisation_id=organisation_id, name=name, code=code, **fields)
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Branch code {code} is already in use.") from exc
    for weekday, hours in _DEFAULT_HOURS.items():
        db.add(
            BranchOperatingHours(
                branch_id=branch.id,
                organisation_id=organisation_id,
                weekday=weekday,
                is_closed=hours is None,
                opens_at=hours[0] if hours else None,
                closes_at=hours[1] if hours else None,
            )
        )
    return branch


def _get_branch_for(
    db: Session, principal: Principal, branch_id: uuid.UUID, permission: str
) -> Branch:
    branch = get_scoped(db, Branch, branch_id, principal.organisation_id)
    principal.require(permission, branch.id)
    return branch


def list_branches(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    search: str | None = None,
    include_archived: bool = False,
) -> tuple[list[Branch], int]:
    if not principal.can_in_any_branch(P.BRANCHES_VIEW):
        raise PermissionDeniedError("You do not have permission to view branches.")
    stmt = select(Branch).where(Branch.organisation_id == principal.organisation_id)
    allowed = principal.branch_ids_with(P.BRANCHES_VIEW)
    if allowed is not None:
        stmt = stmt.where(Branch.id.in_(allowed))
    if not include_archived:
        stmt = stmt.where(Branch.archived_at.is_(None))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(Branch.name.ilike(pattern), Branch.code.ilike(pattern)))
    return paginate(db, stmt.order_by(Branch.archived_at.is_not(None), Branch.name), params)


def get_branch(db: Session, principal: Principal, branch_id: uuid.UUID) -> Branch:
    return _get_branch_for(db, principal, branch_id, P.BRANCHES_VIEW)


def get_operating_hours(db: Session, branch: Branch) -> list[BranchOperatingHours]:
    return list(
        db.scalars(
            select(BranchOperatingHours)
            .where(BranchOperatingHours.branch_id == branch.id)
            .order_by(BranchOperatingHours.weekday)
        )
    )


def create_branch(db: Session, principal: Principal, body: BranchCreate) -> Branch:
    principal.require(P.BRANCHES_MANAGE)  # organisation-wide only
    data = body.model_dump()
    branch = create_branch_record(db, principal.organisation_id, **data)
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        actor=principal,
        action="branch.created",
        entity_type="branch",
        entity_id=branch.id,
        summary=f"Branch {branch.name} ({branch.code}) created",
        changes=data,
    )
    db.commit()
    return branch


def update_branch(
    db: Session, principal: Principal, branch_id: uuid.UUID, body: BranchUpdate
) -> Branch:
    branch = _get_branch_for(db, principal, branch_id, P.BRANCHES_MANAGE)
    changes = apply_changes(branch, body.changes())
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Branch code is already in use.") from exc
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            branch_id=branch.id,
            actor=principal,
            action="branch.updated",
            entity_type="branch",
            entity_id=branch.id,
            summary=f"Branch {branch.name} updated",
            changes=changes,
        )
    db.commit()
    return branch


def set_archived(db: Session, principal: Principal, branch_id: uuid.UUID, archived: bool) -> Branch:
    principal.require(P.BRANCHES_MANAGE)  # organisation-wide only
    branch = get_scoped(db, Branch, branch_id, principal.organisation_id)
    if archived == (branch.archived_at is not None):
        return branch
    if archived:
        active_count = db.scalar(
            select(func.count())
            .select_from(Branch)
            .where(
                Branch.organisation_id == principal.organisation_id, Branch.archived_at.is_(None)
            )
        )
        if active_count == 1:
            raise ConflictError("An organisation must keep at least one active branch.")
    branch.archived_at = utcnow() if archived else None
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        actor=principal,
        action="branch.archived" if archived else "branch.restored",
        entity_type="branch",
        entity_id=branch.id,
        summary=f"Branch {branch.name} {'archived' if archived else 'restored'}",
    )
    db.commit()
    return branch


def set_operating_hours(
    db: Session, principal: Principal, branch_id: uuid.UUID, body: OperatingHoursUpdate
) -> list[BranchOperatingHours]:
    branch = _get_branch_for(db, principal, branch_id, P.BRANCHES_MANAGE)
    before = {
        h.weekday: [h.is_closed, h.opens_at, h.closes_at] for h in get_operating_hours(db, branch)
    }
    db.execute(delete(BranchOperatingHours).where(BranchOperatingHours.branch_id == branch.id))
    for day in body.days:
        db.add(
            BranchOperatingHours(
                branch_id=branch.id,
                organisation_id=principal.organisation_id,
                weekday=day.weekday,
                is_closed=day.is_closed,
                opens_at=day.opens_at,
                closes_at=day.closes_at,
            )
        )
    after = {d.weekday: [d.is_closed, d.opens_at, d.closes_at] for d in body.days}
    changes = {str(k): [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            branch_id=branch.id,
            actor=principal,
            action="branch.hours_updated",
            entity_type="branch",
            entity_id=branch.id,
            summary=f"Operating hours updated for {branch.name}",
            changes=changes,
        )
    db.commit()
    return get_operating_hours(db, branch)


def list_service_bays(db: Session, principal: Principal, branch_id: uuid.UUID) -> list[ServiceBay]:
    branch = _get_branch_for(db, principal, branch_id, P.BRANCHES_VIEW)
    return list(
        db.scalars(
            select(ServiceBay)
            .where(ServiceBay.branch_id == branch.id)
            .order_by(ServiceBay.is_active.desc(), ServiceBay.name)
        )
    )


def create_service_bay(
    db: Session, principal: Principal, branch_id: uuid.UUID, body: ServiceBayCreate
) -> ServiceBay:
    branch = _get_branch_for(db, principal, branch_id, P.BRANCHES_MANAGE)
    bay = ServiceBay(
        organisation_id=principal.organisation_id, branch_id=branch.id, **body.model_dump()
    )
    db.add(bay)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A service bay with this name already exists at this branch.") from exc
    audit.record(
        db,
        organisation_id=principal.organisation_id,
        branch_id=branch.id,
        actor=principal,
        action="service_bay.created",
        entity_type="service_bay",
        entity_id=bay.id,
        summary=f"Service bay {bay.name} added to {branch.name}",
    )
    db.commit()
    return bay


def update_service_bay(
    db: Session,
    principal: Principal,
    branch_id: uuid.UUID,
    bay_id: uuid.UUID,
    body: ServiceBayUpdate,
) -> ServiceBay:
    branch = _get_branch_for(db, principal, branch_id, P.BRANCHES_MANAGE)
    bay = get_scoped(db, ServiceBay, bay_id, principal.organisation_id)
    if bay.branch_id != branch.id:
        raise ConflictError("Service bay does not belong to this branch.")
    changes = apply_changes(bay, body.changes())
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A service bay with this name already exists at this branch.") from exc
    if changes:
        audit.record(
            db,
            organisation_id=principal.organisation_id,
            branch_id=branch.id,
            actor=principal,
            action="service_bay.updated",
            entity_type="service_bay",
            entity_id=bay.id,
            summary=f"Service bay {bay.name} updated",
            changes=changes,
        )
    db.commit()
    return bay
