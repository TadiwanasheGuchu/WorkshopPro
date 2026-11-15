"""Audit trail writer.

Call `record()` inside the same transaction as the change it describes, so the audit
entry and the change commit or roll back together.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.context import client_ip_var, request_id_var
from app.models import AuditLog
from app.permissions.principal import Principal


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID | Decimal | datetime | date | time):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return value


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """{"field": [old, new]} for fields whose value changed."""
    return {
        key: [_jsonable(before.get(key)), _jsonable(after[key])]
        for key in after
        if before.get(key) != after[key]
    }


def record(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    summary: str,
    actor: Principal | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    branch_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        organisation_id=organisation_id,
        branch_id=branch_id,
        actor_user_id=actor.user_id if actor else actor_user_id,
        actor_type=actor_type or ("user" if (actor or actor_user_id) else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:300],
        changes=_jsonable(changes) if changes else None,
        ip_address=client_ip_var.get(),
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
