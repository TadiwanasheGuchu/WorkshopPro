import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession, Paging
from app.schemas.audit import AuditLogRead
from app.schemas.common import Page
from app.services import audit_queries

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get(
    "",
    response_model=Page[AuditLogRead],
    summary="Audit log",
    description=(
        "Newest first. `action` matches exactly, or as a prefix when it ends with a dot "
        "(e.g. `user.`). Date range is [created_from, created_to)."
    ),
)
def list_audit_logs(
    principal: CurrentPrincipal,
    db: DbSession,
    paging: Paging,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Page[AuditLogRead]:
    items, total = audit_queries.list_audit_logs(
        db,
        principal,
        paging,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        created_from=created_from,
        created_to=created_to,
    )
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)
