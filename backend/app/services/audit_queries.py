"""Read side of the audit log."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Branch, User
from app.permissions.catalogue import P
from app.permissions.principal import Principal
from app.schemas.audit import AuditLogRead
from app.schemas.common import PageParams


def list_audit_logs(
    db: Session,
    principal: Principal,
    params: PageParams,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[AuditLogRead], int]:
    principal.require(P.AUDIT_VIEW)
    conditions = [AuditLog.organisation_id == principal.organisation_id]
    if action:
        # "user." matches every user action; "user.invited" matches exactly.
        conditions.append(
            AuditLog.action.startswith(action)
            if action.endswith(".")
            else AuditLog.action == action
        )
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_user_id:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if created_from:
        conditions.append(AuditLog.created_at >= created_from)
    if created_to:
        conditions.append(AuditLog.created_at < created_to)

    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = db.execute(
        select(AuditLog, User.full_name, Branch.name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .outerjoin(Branch, Branch.id == AuditLog.branch_id)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    items = [
        AuditLogRead(
            id=log.id,
            created_at=log.created_at,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            summary=log.summary,
            changes=log.changes,
            actor_type=log.actor_type,
            actor_user_id=log.actor_user_id,
            actor_name=actor_name,
            branch_id=log.branch_id,
            branch_name=branch_name,
            ip_address=str(log.ip_address) if log.ip_address else None,
            request_id=log.request_id,
        )
        for log, actor_name, branch_name in rows
    ]
    return items, total
